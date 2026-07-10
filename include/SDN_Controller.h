#ifndef SDN_CONTROLLER_H
#define SDN_CONTROLLER_H

#include <systemc.h>
#include <vector>
#include <map>
#include <set>
#include "arbitro.h"
#include "definitions.h"
#include "ControlUnit.h"
#include "TopologyManager.h"
#include "ControlAggregator.h"
#include "StatsCollector.h"



SC_MODULE(SDN_Controller) {
    int num_cus;
    sc_in_clk clk;
    
    sc_fifo_in<PacketMetadata> requisitions_in;


    // Porta para receber o aviso de fim de transmissão do Injetor
    sc_fifo_in<int> teardown_in;

    // Saída final para o injetor.
    sc_fifo_out<int> path_ready_out;

    // Conexões Internas
    //sc_fifo<PacketMetadata> internal_fifo_to_arb;
    // Vetor de FIFOs que ligam o árbitro ás CUs.
    sc_vector<sc_fifo<PacketMetadata>> cu_buses;

    // É o canal (FIFO) entre ControlUnit e ControlAggregator.
    sc_vector<sc_fifo<int>> internal_ready_buses;

    Arbitro* arb;
    sc_vector<ControlUnit> cus;

    TopologyManager* tm;
    const NetworkConfig* cfg;
    ControlAggregator* aggregator;

    sc_vector<sc_fifo_out<SwitchConfigCmd>> router_config_out;
    std::map<int, std::vector<int>> active_paths;

    // --- Confirmação (ACK) de aplicação de comandos, por roteador ---
    // Substitui o antigo "wait de margem fixa" (control_plane_latency + 1ns)
    // por uma confirmação real: cada LocalAgent avisa aqui quando de fato
    // aplicou seu comando. Sem isso, o SDN não tinha como saber se um
    // roteador estava com a fila de comandos ocupada processando um
    // fluxo anterior, o que atrasava a aplicação real além da margem
    // assumida (foi exatamente a causa do bug do fluxo 35).
    sc_vector<sc_fifo_in<int>> router_config_ack_in;

    // flow_id -> conjunto de índices de roteador que já confirmaram
    // (via ACK) a aplicação do comando mais recente para este fluxo.
    std::map<int, std::set<int>> acked_routers_by_flow;
    sc_mutex ack_mutex;
    sc_event ack_event;

    // Usado só para reportar fluxos descartados por esgotar max_retries
    // (problema #8). O ControlUnit não tem acesso direto ao StatsCollector
    // -- ele passa pelo parent_sdn (já existente), evitando editar
    // ControlUnit.h.
    StatsCollector* stats = nullptr;

    SDN_Controller(sc_module_name name, int num_cus, int num_routers);
    //void bridge_port_to_fifo();
    void set_topology(TopologyManager* _tm);
    void set_config(const NetworkConfig* _cfg);
    void set_stats(StatsCollector* _stats);
    void configure_path_hardware(const std::vector<int>& route, int flow_id);
    void process_teardown();

    // Uma instância desta thread roda por roteador, ouvindo continuamente
    // seu canal de ACK e registrando as confirmações em acked_routers_by_flow.
    void ack_listener_process(int router_index);

    // Bloqueia (a thread chamadora, tipicamente um ControlUnit ou o
    // process_teardown) até que TODOS os roteadores em `route` tenham
    // confirmado a aplicação do comando mais recente para `flow_id`.
    // Limpa o estado ao final, para a próxima rodada (setup ou teardown)
    // começar do zero.
    void wait_for_route_ack(int flow_id, const std::vector<int>& route);

    // Chamado por um ControlUnit quando ele desiste de rotear um fluxo após
    // esgotar max_retries. Registra o descarte no StatsCollector para que o
    // fluxo apareça explicitamente como DESCARTADO_TIMEOUT no relatório
    // final, em vez de simplesmente ficar preso/desaparecer.
    void report_flow_discarded(int flow_id);
};
#endif