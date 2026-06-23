#include <systemc.h>
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <vector>
#include "ControlUnit.h"
#include "definitions.h"
#include "TopologyManager.h"
#include "arbitro.h"
#include "router.h"
#include "dijkstra.h"
#include "TrafficInjector.h"
#include "StatsCollector.h"
#include "SDN_Controller.h"
#include "TrafficUtils.h"

using json = nlohmann::json;

int sc_main(int argc, char* argv[]) {
    sc_clock clk("clk", 10, SC_NS);
    sc_signal<bool> rst("rst");
    rst.write(false);

    StatsCollector stats;
    
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
    /*
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
    */
    // ---------------------------------------

    // =========================================================================
    // 4. INSTANCIAÇÃO DOS CANAIS E SINAIS DE CONEXÃO
    // =========================================================================
    // --- Canais do Plano de Controle Global ---
    sc_fifo<PacketMetadata> request_fifo("request_fifo", 1000);
    sc_fifo<int> path_ready_fifo("path_ready_fifo", 1000);

    // --- Canal para o Injetor avisar o SDN que o fluxo terminou ---
    sc_fifo<int> teardown_fifo("teardown_fifo", 1000);

    // --- Fios Ponto-a-Ponto (Alocados dinamicamente) ---
    // Canais entre o SDN e os Roteadores (Plano de Controle Local)
    std::vector<sc_fifo<SwitchConfigCmd>*> sdn_to_router_fifos(num_nodes);
    
    // Canais entre o Injetor de Tráfego e as Portas Locais dos Roteadores
    std::vector<sc_fifo<Flit>*> ti_to_router_fifos(num_nodes);
    std::vector<sc_fifo<Flit>*> router_to_ti_fifos(num_nodes);

    // Inicializa os canais de comunicação estritos
    for(int i = 0; i < num_nodes; ++i) {
        sdn_to_router_fifos[i] = new sc_fifo<SwitchConfigCmd>(("sdn_2_R" + std::to_string(i)).c_str(), 1000);
        ti_to_router_fifos[i]  = new sc_fifo<Flit>(("ti_2_R" + std::to_string(i)).c_str(), 1000);
        router_to_ti_fifos[i]  = new sc_fifo<Flit>(("R" + std::to_string(i) + "_2_ti").c_str(), 1000);
    }

    // Estrutura para salvar os FIFOs da malha (fabric) e deletar depois
    std::vector<sc_fifo<Flit>*> fabric_fifos;

    // =========================================================================
    // 5. INSTANCIAÇÃO E CONEXÃO DOS MÓDULOS
    // =========================================================================
    // 5.1 Instanciando os Roteadores
    std::vector<Router*> routers(num_nodes);
    for(int i = 0; i < num_nodes; ++i) {
        routers[i] = new Router(("Router_" + std::to_string(i)).c_str(), net_cfg);
        routers[i]->clk(clk);
        routers[i]->config_in(*sdn_to_router_fifos[i]); // Ouve o canal do SDN
    }

    // =========================================================================
    // 5.2 Fazendo a Cablagem (Bind) baseada na Topologia
    // =========================================================================
    for (int i = 0; i < num_nodes; ++i) {
        for (int p = 0; p < NUM_PORTS; ++p) {
            
            // Tratamento especial para a porta LOCAL
            if (p == PORT_LOCAL) {
                routers[i]->flit_in[PORT_LOCAL](*ti_to_router_fifos[i]);
                routers[i]->flit_out[PORT_LOCAL](*router_to_ti_fifos[i]);
                continue; 
            }

            // Tratamento dinâmico para as demais portas
            int vizinho = tm->get_neighbor_at_port(i, p);
            if (vizinho != -1) {
                // --- PORTA CONECTADA: Cria o canal real da malha ---
                std::string fifo_name = "link_R" + std::to_string(i) + "_p" + std::to_string(p);
                sc_fifo<Flit>* link_fifo = new sc_fifo<Flit>(fifo_name.c_str(), 1000);
                fabric_fifos.push_back(link_fifo); 

                // Roteador 'i' envia dados por este canal
                routers[i]->flit_out[p](*link_fifo);
                
                // Roteador 'vizinho' lê os dados deste canal na sua porta reversa
                int reverse_port = tm->get_port_to_neighbor(vizinho, i);
                routers[vizinho]->flit_in[reverse_port](*link_fifo);
            } else {
                // --- PORTA DE BORDA (SEM VIZINHO): Conecta a canais dummy ---
                // Criamos um canal sem saída para a entrada e outro para a saída
                std::string dummy_in_nm  = "dummy_in_R"  + std::to_string(i) + "_p" + std::to_string(p);
                std::string dummy_out_nm = "dummy_out_R" + std::to_string(i) + "_p" + std::to_string(p);
                
                sc_fifo<Flit>* d_in  = new sc_fifo<Flit>(dummy_in_nm.c_str(), 1000);
                sc_fifo<Flit>* d_out = new sc_fifo<Flit>(dummy_out_nm.c_str(), 1000);
                
                // Guarda na lista para o delete final não esquecer deles
                fabric_fifos.push_back(d_in);
                fabric_fifos.push_back(d_out);

                // Amarra as portas soltas do Roteador nesses FIFOs isolados
                routers[i]->flit_in[p](*d_in);
                routers[i]->flit_out[p](*d_out);
            }
        }
    }

    // 5.3 Instanciação e Conexão do Injetor de Tráfego
    std::string traffic_mode = cfg["traffic"]["mode"]; // "deterministic" ou "uniform"
    TrafficInjector* ti = new TrafficInjector("Traffic_Injector", num_nodes, net_cfg, &stats);
    std::string csv_path;

    if(traffic_mode == "deterministic"){
        csv_path = cfg["traffic"]["source_file"];
    } else if (traffic_mode == "uniform"){
        int seed = cfg["traffic"].value("seed", 1);
        int num_packets = cfg["traffic"].value("num_packets", 1000);
        generateUniformTraffic(num_nodes, num_packets, seed, "uniform.csv");
        csv_path = "uniform.csv";
    }else{
        std::cerr << "Erro: Modo de trafego desconhecido: " << traffic_mode << std::endl;
        return 1;
    }

    ti->load_traffic_from_csv(csv_path);
    
    ti->clk(clk);
    ti->rst(rst);
    ti->request_to_sdn(request_fifo);
    ti->path_ready_in(path_ready_fifo); 

    // Bind da saída de teardown do Injetor para o FIFO
    ti->teardown_to_sdn(teardown_fifo);

    for(int i = 0; i < num_nodes; ++i) {
        // Conecta as portas do Injetor aos canais que vão para os Roteadores
        ti->data_out[i](*ti_to_router_fifos[i]);
        ti->data_in[i](*router_to_ti_fifos[i]);
    }

    // 5.4 Instanciação e Conexão do SDN Controller
    SDN_Controller* sdn = new SDN_Controller("SDN_Controller", num_cu, tm->get_num_nodes());
    sdn->clk(clk);
    sdn->set_topology(tm);
    sdn->set_config(&net_cfg);
    
    sdn->requisitions_in(request_fifo);
    sdn->path_ready_out(path_ready_fifo);
    
    // Bind da entrada de teardown do SDN lendo do FIFO
    sdn->teardown_in(teardown_fifo);

    // Conectando o plano de controle de saída do SDN aos canais dos roteadores
    for(int i = 0; i < num_nodes; ++i) {
        // Presumindo que seu SDN possui um array de portas chamado 'config_out'
        sdn->router_config_out[i](*sdn_to_router_fifos[i]); 
    }
    
    // =========================================================================
    // 6. EXECUÇÃO DA SIMULAÇÃO
    // =========================================================================
    std::cout << "Iniciando a simulacao do sistema..." << std::endl;
    
    sc_start(10, SC_US);
    
    std::cout << "Simulacao finalizada com sucesso." << std::endl;

    stats.generate_report("results.csv");

    // Desalocação segura de memória (Evitando leaks no C++)
    delete tm;
    delete ti;
    delete sdn;
    
    for (auto router : routers) delete router;
    for (auto fifo : sdn_to_router_fifos) delete fifo;
    for (auto fifo : ti_to_router_fifos) delete fifo;
    for (auto fifo : router_to_ti_fifos) delete fifo;
    for (auto fifo : fabric_fifos) delete fifo;

    return 0;
    
}