#ifndef DEFINITIONS_H
#define DEFINITIONS_H

#include <iostream>
#include <vector>
#include <systemc.h>
#include "flit.h"
#include <map>
#include <string>

// Tentativas FALHAS de alocacao de rota por fluxo (retries). Escrito pela
// ControlUnit, lido pelo StatsCollector. Threads SystemC sao cooperativas
// (sem concorrencia real), entao nao precisa de mutex.
inline std::map<int, int>& flow_retry_counts() {
    static std::map<int, int> m;
    return m;
}

// ---- Rastreamento opcional (trace). Desligado por padrao. ----
// Ligado por network_params.trace_flow_ids + trace_file (ver main.cpp).
// Nao usa wait(): nao altera o tempo simulado.
#include <set>
#include <fstream>
#include <sstream>
inline std::set<int>& trace_flow_ids() { static std::set<int> s; return s; }  // -1 = todos
inline std::ofstream& trace_out() { static std::ofstream f; return f; }
inline bool trace_enabled() { return trace_out().is_open(); }
inline bool trace_flow(int id) {
    return trace_enabled() && (trace_flow_ids().count(id) > 0 || trace_flow_ids().count(-1) > 0);
}
// Porta de entrada em que cada OutputMUX esta bloqueado lendo (-1 = nenhuma).
inline std::map<std::string, int>& mux_blocked_port() { static std::map<std::string, int> m; return m; }
inline std::string trace_route_str(const std::vector<int>& r) {
    std::ostringstream os;
    for (size_t i = 0; i < r.size(); ++i) os << r[i] << (i + 1 < r.size() ? "->" : "");
    return os.str();
}
#define TRACE_LOG(expr) do { if (trace_enabled()) { trace_out() << "@" << sc_core::sc_time_stamp() << " " << expr << std::endl; } } while (0)
#define TRACE_FLOW(fid, expr) do { if (trace_flow(fid)) { TRACE_LOG(expr); } } while (0)

inline std::ostream& operator<<(std::ostream& os, const std::vector<int>& v) {
    os << "[ ";
    for (size_t i = 0; i < v.size(); ++i) {
        os << v[i] << (i < v.size() - 1 ? ", " : " ");
    }
    os << "]";
    return os;
}

struct PathWrapper {
    std::vector<int> path;

    // Construtores para facilitar o uso
    PathWrapper() {}
    PathWrapper(std::vector<int> p) : path(p) {}

    // O SystemC exige este operador para o sc_fifo::print funcionar
    friend std::ostream& operator<<(std::ostream& os, const PathWrapper& pw) {
        os << "[ ";
        for (int node : pw.path) {
            os << node << " ";
        }
        os << "]";
        return os;
    }
};

// Estrutura para estatísticas/metadados (usada para contagem e SDN)
struct PacketMetadata {
    int total_flits;
    int flow_id;
    int sender_id;
    int receiver_id;
    int in_port;
    sc_time tempo_requisicao;
    bool requisicao_registrada;

    // Construtor padrão (Obrigatório para canais SystemC)
    PacketMetadata() : total_flits(0), flow_id(0), sender_id(0), receiver_id(0), in_port(0),
                    tempo_requisicao(SC_ZERO_TIME), requisicao_registrada(false) {}

    bool operator==(const PacketMetadata& other) const {
        return (total_flits == other.total_flits &&
                flow_id == other.flow_id &&
                sender_id == other.sender_id &&
                receiver_id == other.receiver_id &&
                in_port == other.in_port &&
                tempo_requisicao == other.tempo_requisicao);
    }

    bool operator!=(const PacketMetadata& other) const {
        return !(*this == other);
    }

    PacketMetadata& operator=(const PacketMetadata& other) {
        if (this != &other) {
            total_flits = other.total_flits;
            flow_id = other.flow_id;
            sender_id = other.sender_id;
            receiver_id = other.receiver_id;
            in_port = other.in_port;
            tempo_requisicao = other.tempo_requisicao;
            requisicao_registrada = other.requisicao_registrada;
        }
        return *this;
    }
};

inline void sc_trace(sc_trace_file* tf, const PacketMetadata& meta, const std::string& name) {
    // Você pode decidir como o Metadata aparecerá no gráfico de ondas:
    // Opção A: Rastrear apenas um campo principal (se for um inteiro, por exemplo)
    sc_trace(tf, meta.flow_id, name + ".flow_id");
    sc_trace(tf, meta.sender_id, name + ".sender_id");
    sc_trace(tf, meta.receiver_id, name + ".receiver_id");
}

inline std::ostream& operator<<(std::ostream& os, const PacketMetadata& meta) {
    os << "PacketMetadata(Flow: " << meta.flow_id 
       << ", Src: " << meta.sender_id 
       << ", Dst: " << meta.receiver_id 
       << ", T_req: " << meta.tempo_requisicao
       << ", Flits: " << meta.total_flits << ")";
    return os;
}

inline void sc_trace(sc_trace_file* tf, const std::vector<int>& v, const std::string& name) {
    // Opcional: implementar rastreamento real se precisar ver o vetor no .vcd
}

struct PortSignals {
    // Sinais de SAÍDA (O Roteador escreve aqui para enviar ao vizinho)
    sc_signal<Flit>* out_data = nullptr;
    sc_signal<bool>* out_valid = nullptr;
    sc_signal<bool>* out_ready_in = nullptr; // Ready que vem do vizinho

    // Sinais de ENTRADA (O Roteador lê aqui o que vem do vizinho)
    sc_signal<Flit>* in_data = nullptr;
    sc_signal<bool>* in_valid = nullptr;
    sc_signal<bool>* in_ready_out = nullptr;
};

// Definição de constantes úteis
const int NUM_PORTS = 5; // N, S, L, O, Local
const int BUFFER_SIZE = 16;
const sc_time CLOCK_PERIOD(10, SC_NS);

// Latência do InputBuffer (1 estágio de "chegada no buffer"). Antes era
// 1ns hardcoded, sem relação com o clock -- agora é literalmente 1 ciclo,
// por decisão explícita (ver levantamento de constantes de tempo): num
// roteador circuito-comutado (rota já configurada pelo SDN, sem
// computação de rota nem arbitragem de canal por flit), os únicos dois
// estágios físicos que restam são "chegou no buffer" (este) e "atravessou
// o link" (link_transit_latency, abaixo) -- 1 ciclo cada é consistente
// com a literatura de roteadores síncronos.
const sc_time LAT = CLOCK_PERIOD;

struct NetworkConfig {
    // Latência de trânsito de um link físico, em ciclos de clock. Antes
    // era lido como "link_transit_latency_ns" (nanosegundos crus, sem
    // garantia de ser múltiplo do período de clock). Convertido para
    // sc_time em main.cpp como link_transit_latency_cycles * CLOCK_PERIOD.
    sc_time link_transit_latency;

    int max_retries;
    int packets_per_flow;
    int flits_per_packet;

    // Tempo ocioso entre pacotes de um mesmo fluxo, em ciclos de clock.
    // Já se chamava "idle_cycles" antes, mas era aplicado como
    // wait(idle_cycles, SC_NS) -- nanosegundos crus com nome de ciclos.
    // Agora é genuinamente ciclos: wait(CLOCK_PERIOD * idle_cycles).
    int idle_cycles;

    // Profundidade (em flits) dos FIFOs do plano de DADOS: injetor<->roteador
    // e roteador<->roteador (malha/fabric). Antes esse valor estava hardcoded
    // em 1000 no main.cpp, o que na prática desativava qualquer backpressure
    // real (um fluxo inteiro nunca chega perto de 1000 flits em trânsito).
    // Usamos BUFFER_SIZE como default caso o JSON não especifique.
    int buffer_size = BUFFER_SIZE;

    // --- Coeficientes do modelo de custo do Dijkstra (ControlUnit) ---
    // O tempo de cálculo de rota escala com o trabalho real do algoritmo:
    // O((V + E) log V). Reformulado para ciclos "de verdade": cada
    // operação elementar custa NO MÍNIMO 1 ciclo inteiro (não dá pra fazer
    // trabalho em menos que isso) -- ver levantamento de constantes de
    // tempo. Isso também absorveu o antigo wait(5,SC_NS) de "decodificação"
    // da requisição (dijkstra_dispatch_cycles), que era um custo fixo
    // desconectado do modelo -- agora há um só lugar de custo algorítmico.

    // Custo fixo de despacho/decodificação da requisição, pago 1x por
    // chamada (substitui o antigo wait(5,SC_NS) hardcoded no ControlUnit).
    int dijkstra_dispatch_cycles = 1;

    // Custo de inicialização O(V): alocar/zerar dist[] e prev[], por nó.
    int dijkstra_init_cycles_per_node = 1;

    // Custo BASE de uma operação de heap (push/pop na priority_queue),
    // escalado por log2(tamanho da fila) -- com mínimo de 1 ciclo por
    // operação, mesmo quando o fator log2 arredondaria para menos.
    int dijkstra_pq_op_cycles = 1;

    // Custo de examinar uma aresta candidata (olhar o vizinho + consultar
    // o estado do link via is_link_busy). Mínimo 1 ciclo por aresta.
    int dijkstra_edge_check_cycles = 1;
    // true: o Dijkstra para ao extrair o destino (custo depende da distancia);
    // false: explora o grafo todo (custo independente da topologia) -- ablacao.
    bool dijkstra_early_exit = true;

    // Algoritmo de roteamento do plano de controle (fator experimental):
    //   "dijkstra"  : Dijkstra com heap (modelo original; custo O((V+E)log V))
    //   "bfs"       : busca em largura com fila FIFO. Equivalente ao Dijkstra
    //                 com pesos unitarios (mesmos caminhos minimos), mas sem
    //                 heap: push/pop custam dijkstra_pq_op_cycles FIXOS (sem
    //                 log2) => custo quase independente da topologia.
    //   "bfs_free"  : mesmo BFS, com custo ZERO de computacao (so o
    //                 dijkstra_dispatch_cycles). Isola o efeito da TOPOLOGIA
    //                 (controle ideal/instantaneo).
    // Respeita dijkstra_early_exit e evita links ocupados nos tres casos.
    std::string routing_algorithm = "dijkstra";

    // Latência de propagação do PLANO DE CONTROLE, em ciclos: tempo entre
    // o SDN Controller escrever um SwitchConfigCmd e o LocalAgent do
    // roteador efetivamente aplicar a configuração no hardware
    // (mux_sel/mux_enable/buffer_target). Antes era ns crus (5ns, nem
    // múltiplo do período de clock); default 0 preserva o comportamento
    // "instantâneo" antigo se não setado.
    sc_time control_plane_latency = SC_ZERO_TIME;

    // Espera de retry, em ciclos: tempo entre uma tentativa de alocação de
    // caminho falhar e a próxima tentativa começar.
    int retry_wait_cycles = 0;

    // Jitter máximo, em ciclos, somado ao retry_wait_cycles de cada
    // ControlUnit. Sem isso, vários fluxos que colidem no mesmo link
    // re-tentam sempre no mesmo instante simulado, gerando um "thundering
    // herd" artificial que não existe num sistema real. O valor efetivo de
    // espera de cada retry é sorteado uniformemente em
    // [retry_wait_cycles, retry_wait_cycles + retry_jitter_cycles]. Se não
    // vier do JSON, main.cpp usa um default proporcional a
    // retry_wait_cycles (25%) em vez de 0.
    int retry_jitter_cycles = 0;

    // Latência de arbitragem (round-robin entre ControlUnits), em ciclos.
    // Antes era wait(1,SC_NS) hardcoded no Arbitro, com um comentário no
    // próprio código original ("Ou defina um valor via cfg") indicando que
    // ficou pendente de calibração. Agora é configurável de verdade.
    int arbitro_latency_cycles = 1;

    // Seed mestre da simulação. Combinado com o hash do nome de cada
    // ControlUnit para semear o RNG do jitter de retry. Sem isso, duas
    // "réplicas" da simulação (rodando o mesmo binário duas vezes) dariam
    // exatamente o mesmo resultado, porque o RNG só dependia do nome do
    // módulo (fixo). Trocar essa seed entre execuções é o que torna cada
    // réplica estatisticamente independente. Lido de simulation.seed no
    // config.json (default 1 preserva reprodutibilidade se não setado).
    unsigned int master_seed = 1;
};

struct TrafficEvent {
    int src;
    int dst;
    double start_time_ns;
    int flow_id;
};

enum ConfigAction {SETUP, RELEASE};

struct SwitchConfigCmd{
    ConfigAction action;
    int output_port; // Qual MUX de saída configurar (ex: porta que vai pro próximo nó)
    int input_port; // Qual porta de entrada selecionar (ex: porta que vem do nó anterior)
    bool enable;
    int flow_id;
};

inline std::ostream& operator<<(std::ostream& os, const SwitchConfigCmd& cmd) {
    os << "Cmd(action=" << cmd.action 
       << ", in=" << cmd.input_port 
       << ", out=" << cmd.output_port << ")";
    return os;
}

enum PortID {
    PORT_LOCAL = 0,
    PORT_NORTH = 1,
    PORT_SOUTH = 2,
    PORT_EAST = 3,
    PORT_WEST = 4
};

enum TrafficMode{
    DETERMINISTIC,
    UNIFORM,
    RANDOM
};

#endif