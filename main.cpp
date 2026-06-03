#include <systemc.h>
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <string>
#include <memory>
#include "ControlUnit.h"
#include "definitions.h"
#include "TopologyManager.h"
#include "arbitro.h"
#include "router.h"
#include "dijkstra.h"
#include "TrafficInjector.h"
#include "SDN_Controller.h"


using json = nlohmann::json;



int sc_main(int argc, char* argv[]) {
    sc_clock clk("clk", 10, SC_NS);
    sc_signal<bool> rst("rst");
    rst.write(false);
    
    // Carregamento do JSON
    std::ifstream file("config.json");
    if(!file.is_open()){
        std::cerr << "ERRO: Nao foi possivel abrir o arquivo config.json" << std::endl;
        return 1;
    }

    json cfg;
    try{
        file >> cfg;
    } catch (json::parse_error& e){
        std::cerr << "Erro: Falha ao fazer parse do JSON: " << e.what() << std::endl;
        return 1;
    }

    if(!cfg.contains("network_params") || !cfg.contains("topology")){
        std::cerr << "Erro: JSON incompleto. Faltam network_params ou topology." << std::endl;
        return 1;
    }

    std::cout << "JSON carregado com sucesso!" << std::endl;

    // Leitura do Network Params.
    NetworkConfig net_cfg;
    net_cfg.link_transit_latency = sc_time(cfg["network_params"]["link_transit_latency_ns"], SC_NS);
    net_cfg.max_retries = cfg["network_params"]["max_retries"];
    net_cfg.retry_wait_ns = cfg["network_params"]["retry_wait_ns"];
    net_cfg.flits_per_packet = cfg["network_params"]["flits_per_packet"];
    net_cfg.idle_cycles = cfg["network_params"]["idle_cycles"];
    net_cfg.packets_per_flow = cfg["network_params"]["packets_per_flow"];
    int num_cu = cfg["network_params"]["num_control_units"];

    // Topologia
    TopologyManager* tm = new TopologyManager();
    
    if(cfg.contains("topology") && cfg["topology"].is_array()){
        for(const auto& link : cfg["topology"]){
            int id = link.value("id", -1);
            int u = link.value("u", -1);
            int v = link.value("v", -1);

            if(id != -1 && u != -1 && v != -1){
                tm->add_link(id,u,v);
            }else{
                std::cerr << "Erro: link invalido encontrado no JSON!" << std::endl;
            }
        }
    }else{
        std::cerr << "Erro: Campo 'topology' nao encontrado ou nao e um array!" << std::endl;
        return 1;
    }

    int num_nodes = tm->get_num_nodes();

    // --- DEBUG: Mapeamento de Topologia ---
    std::cout << "\n--- Debug: Topologia e Mapeamento de Portas ---" << std::endl;
    
    // 1. Links (Arestas)
    std::cout << "Links detectados:" << std::endl;
    for (const auto& link : tm->get_links()) {
        std::cout << "Link ID " << link.id << ": " << link.u << " <--> " << link.v << std::endl;
    }

    // 2. Mapeamento de Portas (Para cada nó, verifique suas portas 0 a 4)
    std::cout << "\nMapeamento de Portas por No (Router ID: Porta -> Vizinho):" << std::endl;
    for (int i = 0; i < num_nodes; ++i) {
        std::cout << "Router " << i << ":" << std::endl;
        for (int p = 0; p < NUM_PORTS; ++p) {
            // Consulta o vizinho nesta porta específica
            int vizinho = tm->get_neighbor_at_port(i, p); 
            if (vizinho != -1) {
                std::cout << "  Porta " << p << " -> Conectada ao Router " << vizinho << std::endl;
            } else {
                std::cout << "  Porta " << p << " -> (Sem conexao/Dummy)" << std::endl;
            }
        }
    }
    std::cout << "-----------------------------------------------\n" << std::endl;
    // ---------------------------------------

    TrafficInjector* ti = new TrafficInjector("Traffic_Injector", 16, net_cfg);

    std::string csv_path = cfg["traffic"]["source_file"];

    ti->load_traffic_from_csv(csv_path);

    ti->clk(clk);
    ti->rst(rst);

    sc_signal<PacketMetadata> request_ti_SDN;
    ti->request_to_sdn(request_ti_SDN);

    SDN_Controller* sdn = new SDN_Controller("SDN_Controller", num_cu);
    sdn->clk(clk);
    sdn->requisitions_in(request_ti_SDN);


    std::cout << "Teste..." << std::endl;
    sc_start(100, SC_NS);

    return 0;
}