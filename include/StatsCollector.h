#ifndef STATS_COLLECTOR_H
#define STATS_COLLECTOR_H

#include <systemc.h>
#include <map>
#include <vector>
#include <fstream>
#include <iostream>
#include <cmath>
#include <iomanip>
#include "definitions.h" // TrafficEvent

// Estágio em que um fluxo se encontra. Substitui os antigos booleanos
// soltos (setup_done/end_done), que só conseguiam dizer "completo" ou
// "incompleto" sem indicar EM QUE FASE o fluxo travou.
enum class FlowStatus {
    NOT_STARTED, // Carregado do CSV, mas a simulacao acabou antes de start_time_ns
    REQUESTED,   // Pedido de rota enviado ao SDN, ainda sem caminho alocado
    ROUTED,      // Caminho alocado (setup), payload ainda nao confirmado no destino
    COMPLETED,   // Entregue com sucesso (setup + confirmacao de entrega)
    DISCARDED    // Descartado pela ControlUnit apos esgotar max_retries (ver problema #8)
};

struct FlowLog {
    sc_time start_time = SC_ZERO_TIME;
    sc_time setup_time = SC_ZERO_TIME;
    sc_time end_time = SC_ZERO_TIME;

    FlowStatus status = FlowStatus::NOT_STARTED;

    // Origem/destino/instante agendado (do trafego), p/ diagnostico no CSV
    int src = -1;
    int dst = -1;
    double start_ns = 0.0;
};

class StatsCollector {
private:
    std::map<int, FlowLog> logs;
    sc_mutex log_mutex;

    // Janela de warm-up: fluxos cujo start_time cai dentro dessa janela
    // ainda aparecem no relatório (nunca somem, ver problema #5), mas são
    // excluídos do cálculo da latência média, por representarem o
    // transiente inicial do sistema (buffers vazios, rotas ainda não
    // estabelecidas) e não o regime permanente que normalmente é o que
    // se quer medir.
    sc_time warmup_window = SC_ZERO_TIME;
    sc_time sim_duration = SC_ZERO_TIME;

    static const char* status_to_str(FlowStatus s) {
        switch (s) {
            case FlowStatus::NOT_STARTED: return "NAO_INICIADO";
            case FlowStatus::REQUESTED:   return "PRESO_ROTEAMENTO";
            case FlowStatus::ROUTED:      return "PRESO_TRANSMISSAO";
            case FlowStatus::COMPLETED:   return "COMPLETO";
            case FlowStatus::DISCARDED:   return "DESCARTADO_TIMEOUT";
        }
        return "DESCONHECIDO";
    }

public:
    // Chamado durante a elaboração (antes de sc_start()), sem lock pelo
    // mesmo motivo de register_expected_flows: não há concorrência ainda.
    void set_warmup_window(sc_time w) {
        warmup_window = w;
    }
    // Pré-registra TODOS os fluxos presentes no tráfego carregado, ANTES da
    // simulação começar (chamar logo após load_traffic_from_csv, ainda na
    // fase de elaboração).
    //
    // Sem isso: um fluxo cujo start_time_ns cai depois do fim da janela de
    // sc_start() nunca chega a chamar record_request(), e portanto nunca
    // era inserido no std::map `logs` -- ele desaparecia do relatório sem
    // deixar rastro nenhum (nem "INCOMPLETO"), o que é um viés de
    // sobrevivência silencioso: quanto mais curta a simulação (ou mais
    // lenta a rede), mais fluxos somem sem serem contabilizados.
    void register_expected_flows(const std::vector<TrafficEvent>& traffic_queue) {
        // SEM lock aqui de propósito: este método é chamado em main.cpp
        // ANTES do sc_start() (fase de elaboração). Nesse ponto não existe
        // nenhuma thread SystemC rodando ainda, então não há concorrência
        // real a proteger. Usar sc_mutex aqui dispara
        // "(E521) immediate notification is not allowed during update
        // phase or elaboration", porque sc_mutex::unlock() notifica um
        // evento interno, e notificação imediata não é permitida fora de
        // um processo em execução do kernel. O mutex continua protegendo
        // os métodos abaixo, que sim são chamados de dentro de threads
        // durante a simulação.
        for (const auto& ev : traffic_queue) {
            FlowLog& fl = logs[ev.flow_id]; // cria a entrada com status default NOT_STARTED
            fl.src = ev.src;
            fl.dst = ev.dst;
            fl.start_ns = ev.start_time_ns;
        }
    }

    void record_request(int flow_id, sc_time t){
        log_mutex.lock();
        logs[flow_id].start_time = t;
        logs[flow_id].status = FlowStatus::REQUESTED;
        log_mutex.unlock();
    }

    void record_setup(int flow_id, sc_time t){
        log_mutex.lock();
        logs[flow_id].setup_time = t;
        logs[flow_id].status = FlowStatus::ROUTED;
        log_mutex.unlock();
    }

    void record_finish(int flow_id, sc_time t){
        log_mutex.lock();
        logs[flow_id].end_time = t;
        logs[flow_id].status = FlowStatus::COMPLETED;
        log_mutex.unlock();
    }

    // Reservado para o problema #8: quando uma ControlUnit desiste de rotear
    // um fluxo após esgotar max_retries, ela chama isso para que o fluxo
    // apareça EXPLICITAMENTE como descartado no relatório, em vez de
    // desaparecer silenciosamente (o mesmo viés do register_expected_flows,
    // só que causado por desistência em vez de corte de tempo).
    void record_discarded(int flow_id, sc_time t){
        log_mutex.lock();
        logs[flow_id].end_time = t;
        logs[flow_id].status = FlowStatus::DISCARDED;
        log_mutex.unlock();
    }

    // Duracao total simulada (usada como penalidade p/ fluxos nao concluidos)
    void set_sim_duration(sc_time d) { sim_duration = d; }

    void generate_report(const std::string& filename) {
        if (logs.empty()) return;

        std::ofstream file(filename);
        file << "flow_id,status,in_warmup,control_latency_cycles,data_latency_cycles,total_latency_cycles,retries,src,dst,start_ns\n";

        double total_sum = 0;
        int penalized_flows = 0;      // nao concluidos fora do warm-up
        int completed_flows = 0;      // completos FORA do warm-up (entram na media)
        int completed_in_warmup = 0;  // completos DENTRO do warm-up (excluidos da media)
        int not_started = 0;
        int stuck_routing = 0;
        int stuck_transmission = 0;
        int discarded = 0;
        // Retries (tentativas falhas de alocar rota): dos fluxos concluidos
        // fora do warm-up, e de todos os fluxos que chegaram ao plano de controle
        long long retries_sum_done = 0;
        int done_with_retry = 0, retries_max = 0;
        long long retries_sum_all = 0;
        int reached_cp = 0;
        auto& rc = flow_retry_counts();

        for (auto const& [id, log] : logs) {
            int nret = rc.count(id) ? rc[id] : 0;
            if (log.status != FlowStatus::NOT_STARTED) { reached_cp++; retries_sum_all += nret; }
            if (nret > retries_max) retries_max = nret;
            // Warm-up definido pelo instante em que o fluxo foi SOLICITADO
            // (start_time), nao pelo instante em que terminou -- assim,
            // fluxos "do regime permanente" que so terminam depois de um
            // periodo de congestionamento herdado do warm-up ainda contam
            // como regime permanente, o que faz mais sentido para medir
            // desempenho em estado estacionario.
            bool in_warmup = (warmup_window > SC_ZERO_TIME) && (log.start_time < warmup_window);

            if (log.status == FlowStatus::COMPLETED) {
                // Valores REAIS (fracionários), usados para a media
                // (total_sum) -- arredondar cada fluxo individualmente
                // antes de somar acumularia erro de arredondamento na
                // media final. Só a EXIBIÇÃO por linha é arredondada.
                double control = (log.setup_time - log.start_time).to_double() / CLOCK_PERIOD.to_double();
                double data = (log.end_time - log.setup_time).to_double() / CLOCK_PERIOD.to_double();
                double total = control + data;

                // Arredondamento só para apresentação (ex: reunião com
                // orientador) -- "ciclos fracionários" são tecnicamente
                // corretos aqui (o clock é vestigial, o tempo real é
                // contínuo por baixo), mas confundem numa leitura rápida.
                // Isso é uma aproximação de exibição, não uma mudança na
                // precisão da simulação em si.
                file << id << "," << status_to_str(log.status) << "," << (in_warmup ? 1 : 0) << ","
                     << std::llround(control) << "," << std::llround(data) << "," << std::llround(total) << "," << nret
                     << "," << log.src << "," << log.dst << "," << log.start_ns << "\n";

                if (in_warmup) {
                    completed_in_warmup++;
                } else {
                    total_sum += total; // acumula o valor REAL, não o arredondado
                    retries_sum_done += nret;
                    if (nret > 0) done_with_retry++;
                    completed_flows++;
                }
            } else {
                file << id << "," << status_to_str(log.status) << "," << (in_warmup ? 1 : 0)
                     << ",N/A,N/A,N/A," << nret
                     << "," << log.src << "," << log.dst << "," << log.start_ns << "\n";

                if (!in_warmup) penalized_flows++;
                switch (log.status) {
                    case FlowStatus::NOT_STARTED: not_started++;      break;
                    case FlowStatus::REQUESTED:   stuck_routing++;    break;
                    case FlowStatus::ROUTED:      stuck_transmission++; break;
                    case FlowStatus::DISCARDED:   discarded++;        break;
                    default: break;
                }
            }
        }

        int total_flows = static_cast<int>(logs.size());
        int total_completed = completed_flows + completed_in_warmup;
        double completion_rate = (total_flows > 0)
            ? (100.0 * total_completed / total_flows)
            : 0.0;

        // --- Resumo agregado: antes, essa informação só dava pra ser
        // inferida contando linhas "INCOMPLETO" manualmente no CSV. ---
        file << "\n--- Resumo ---\n";
        file << "Janela de warm-up (ciclos)," << std::llround(warmup_window.to_double() / CLOCK_PERIOD.to_double()) << "\n";
        file << "Total de fluxos no trafego," << total_flows << "\n";
        file << "Completos (total)," << total_completed << "\n";
        file << "Completos dentro do warm-up (excluidos da media)," << completed_in_warmup << "\n";
        file << "Completos em regime permanente (usados na media)," << completed_flows << "\n";
        file << "Nao iniciados (fora da janela de simulacao)," << not_started << "\n";
        file << "Presos em roteamento (aguardando alocacao de rota)," << stuck_routing << "\n";
        file << "Presos em transmissao (rota alocada mas sem confirmacao)," << stuck_transmission << "\n";
        file << "Descartados por timeout de roteamento," << discarded << "\n";
        file << "Taxa de conclusao (%)," << completion_rate << "\n";

        if (completed_flows > 0) {
            // Media calculada sobre os valores REAIS (total_sum), só o
            // resultado final e arredondado para exibição.
            file << "Latencia media regime permanente exclui warmup ciclos," << std::llround(total_sum / completed_flows) << "\n";
        } else {
            file << "Latencia media ciclos,N/A (nenhum fluxo em regime permanente finalizado)\n";
        }

        // --- Metricas p/ otimizacao (GA): sem arredondar e penalizadas ---
        // Penalizada: fluxo nao concluido (fora do warm-up) conta com
        // latencia = duracao total da simulacao (ciclos).
        double sim_cycles = sim_duration.to_double() / CLOCK_PERIOD.to_double();
        int n_eval = completed_flows + penalized_flows;
        file << std::setprecision(10);
        if (completed_flows > 0)
            file << "Latencia media exata sem arredondar ciclos," << (total_sum / completed_flows) << "\n";
        else
            file << "Latencia media exata sem arredondar ciclos,N/A\n";
        file << "Fluxos nao concluidos penalizados," << penalized_flows << "\n";
        file << "Penalidade por fluxo (ciclos)," << sim_cycles << "\n";
        if (n_eval > 0)
            file << "Latencia media penalizada ciclos,"
                 << ((total_sum + penalized_flows * sim_cycles) / n_eval) << "\n";
        else
            file << "Latencia media penalizada ciclos,N/A\n";

        // --- Retries por fluxo (diagnostico da contencao de rotas) ---
        file << "Retries medios por fluxo concluido (regime permanente),"
             << (completed_flows > 0 ? (double)retries_sum_done / completed_flows : 0.0) << "\n";
        file << "Fluxos concluidos com pelo menos 1 retry (%),"
             << (completed_flows > 0 ? 100.0 * done_with_retry / completed_flows : 0.0) << "\n";
        file << "Retries medios por fluxo que chegou ao plano de controle,"
             << (reached_cp > 0 ? (double)retries_sum_all / reached_cp : 0.0) << "\n";
        file << "Retries maximo em um fluxo," << retries_max << "\n";

        file.close();
    }
};

#endif // STATS_COLLECTOR_H