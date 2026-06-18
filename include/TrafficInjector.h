#ifndef TRAFFIC_INJECTOR_H
#define TRAFFIC_INJECTOR_H

#include <systemc.h>
#include <vector>
#include <fstream>
#include <sstream>
#include <random>
#include <map>
#include <nlohmann/json.hpp>
#include "router.h"
#include "definitions.h"
#include <iostream>
#include <algorithm>

using json = nlohmann::json;


SC_MODULE(TrafficInjector) {
    sc_in_clk clk;
    sc_in<bool> rst;

    std::vector<TrafficEvent> traffic_queue; // Lista dos pacotes a enviar.
    
    // --- PLANO DE DADOS (Handshake por porta de roteador) ---
    sc_vector<sc_fifo_out<Flit>> data_out; // Injetor joga o flit aqui. Se o router travar, o código espera.
    sc_vector<sc_fifo_in<Flit>>  data_in;  // Injetor lê o flit aqui quando ele chega no destino.

    // --- PLANO DE CONTROLE (Comunicação com o SDN Controller) ---
    // Porta para solicitar rota (Request)
    sc_fifo_out<PacketMetadata> request_to_sdn;

    // Porta para receber o sinal de "Caminho Pronto" (Start Signal)
    sc_fifo_in<int> path_ready_in; 
    
    // Porta para avisar "Comunicação Terminada" (Release Signal)
    //sc_out<bool>   release_path_signal;

    const NetworkConfig& cfg;

    std::map<int, bool> ready_flows;
    sc_mutex map_mutex;
    sc_event ready_event;
    sc_mutex request_mutex;

    TrafficInjector(sc_module_name name, int num_nodes, const NetworkConfig& config);

    void load_traffic_from_csv(const std::string& filename);

    void run();

    void process_traffic_flow(TrafficEvent event);

    void request_path(TrafficEvent event);

    void wait_for_path_ready(int flow_id);

    void send_data_payload(TrafficEvent event);

    void release_path(int flow_id);

    void monitor_controller_responses();
};

#endif