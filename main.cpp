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

    // =========================================================================
    // 4. INSTANCIAÇÃO DOS CANAIS E SINAIS DE CONEXÃO
    // =========================================================================
    // --- Canais do Plano de Controle (FIFOs) ---
    sc_fifo<PacketMetadata> request_fifo("request_fifo", 100);
    sc_fifo<int> path_ready_fifo("path_ready_fifo", 100);

    /*
    // --- Sinais do Plano de Dados (Dummy para evitar erro de porta solta) ---
    sc_vector<sc_signal<Flit>> data_out_sigs("data_out_sigs", num_nodes);
    sc_vector<sc_signal<bool>> valid_out_sigs("valid_out_sigs", num_nodes);
    sc_vector<sc_signal<bool>> ready_in_sigs("ready_in_sigs", num_nodes);

    sc_vector<sc_signal<Flit>> data_in_sigs("data_in_sigs", num_nodes);
    sc_vector<sc_signal<bool>> valid_in_sigs("valid_in_sigs", num_nodes);
    sc_vector<sc_signal<bool>> ready_out_sigs("ready_out_sigs", num_nodes);
    */

    // --- Plano de Controle: 1 FIFO por Roteador ---
    // O SDN Controller precisa falar individualmente com cada roteador.
    sc_vector<sc_fifo<SwitchConfigCmd>> router_config_fifos("router_config_fifos", num_nodes);

    // --- Plano de Dados: Matriz de Sinais (Tecido de Interconexão) ---
    // Precisamos de um sinal para cada porta de cada roteador.
    // Matriz: [router_id][port_id]
    sc_vector<sc_vector<sc_signal<Flit>>> fabric("fabric", num_nodes);
    for(int i = 0; i < num_nodes; ++i) {
        fabric[i].init(NUM_PORTS);
    }

    // =========================================================================
    // 5. INSTANCIAÇÃO E CONEXÃO DOS MÓDULOS
    // =========================================================================
    // Instanciando Roteadores
    sc_vector<Router*> routers("routers", num_nodes);
    for(int i = 0; i < num_nodes; ++i) {
        routers[i] = new Router(("Router_" + std::to_string(i)).c_str());
        routers[i]->clk(clk);
        routers[i]->config_in(router_config_fifos[i]); // Conecta ao FIFO de controle dele
    }

    // Fazendo a Cablagem (Bind) baseada na Topologia
    for (int i = 0; i < num_nodes; ++i) {
        for (int p = 0; p < NUM_PORTS; ++p) {
            if (p == PORT_LOCAL) {
                // Porta Local: Conectamos ao TrafficInjector futuramente
                // (O Injetor acessará routers[i]->flit_in[PORT_LOCAL])
                continue; 
            }

            int vizinho = tm->get_neighbor_at_port(i, p);
            if (vizinho != -1) {
                // Conectamos a saída do Router[i] na porta p ao sinal da "fabric"
                routers[i]->flit_out[p](fabric[i][p]);
                
                // Conectamos a entrada do vizinho (na porta que aponta de volta para i)
                int reverse_port = tm->get_port_to_neighbor(vizinho, i);
                routers[vizinho]->flit_in[reverse_port](fabric[i][p]);
            }
        }
    }

    // Instanciação do Injetor de Tráfego
    TrafficInjector* ti = new TrafficInjector("Traffic_Injector", num_nodes, net_cfg);
    std::string csv_path = cfg["traffic"]["source_file"];
    ti->load_traffic_from_csv(csv_path);
    
    // Conexões básicas do Injetor
    ti->clk(clk);
    ti->rst(rst);

    // Conexões de Controle do Injetor
    ti->request_to_sdn(request_fifo);
    ti->path_ready_in(path_ready_fifo); // Nova porta que adicionamos

    // Conectando o Injetor à porta LOCAL de cada roteador
    for(int i = 0; i < num_nodes; ++i) {
        ti->data_out[i](routers[i]->flit_in[PORT_LOCAL]);
        ti->data_in[i](routers[i]->flit_out[PORT_LOCAL]);
    }

    // Instanciação do SDN Controller
    SDN_Controller* sdn = new SDN_Controller("SDN_Controller", num_cu, tm->get_num_nodes());
    sdn->clk(clk);
    
    // Conexões de Controle do SDN
    sdn->requisitions_in(request_fifo);
    sdn->path_ready_out(path_ready_fifo);
    
    // Passando referências globais de infraestrutura
    sdn->set_topology(tm);
    sdn->set_config(&net_cfg);
    
    // =========================================================================
    // 6. EXECUÇÃO DA SIMULAÇÃO
    // =========================================================================
    std::cout << "Iniciando a simulacao do sistema..." << std::endl;
    
    sc_start(10, SC_US);
    
    std::cout << "Simulacao finalizada com sucesso." << std::endl;

    // Limpeza de memória
    delete tm;
    delete ti;
    delete sdn;

    return 0;
    
}