#include <systemc.h>
#include <nlohmann/json.hpp>
#include <fstream>
#include <iostream>
#include <vector>
#include <algorithm>
#include <cmath>
#include <cstdlib>
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

    // Todas as latências abaixo agora são lidas em CICLOS DE CLOCK, não
    // nanosegundos crus -- ver levantamento de constantes de tempo. Cada
    // uma é convertida para sc_time multiplicando por CLOCK_PERIOD, ou
    // guardada como inteiro de ciclos quando é somada/sorteada junto com
    // jitter antes de virar sc_time (ex: retry).
    int link_transit_latency_cycles = cfg["network_params"]["link_transit_latency_cycles"];
    net_cfg.link_transit_latency = CLOCK_PERIOD * link_transit_latency_cycles;
    // Alcance do fio em tiles por ciclo (opcional). 0 = desligado: todo link usa
    // link_transit_latency (comportamento anterior). Ver apply_link_length_patch.py.
    const double link_reach_tiles_per_cycle =
        cfg["network_params"].value("link_reach_tiles_per_cycle", 0.0);

    net_cfg.max_retries = cfg["network_params"]["max_retries"];
    net_cfg.retry_wait_cycles = cfg["network_params"]["retry_wait_cycles"];
    net_cfg.flits_per_packet = cfg["network_params"]["flits_per_packet"];
    net_cfg.idle_cycles = cfg["network_params"]["idle_cycles"];
    net_cfg.packets_per_flow = cfg["network_params"]["packets_per_flow"];
    // Profundidade dos FIFOs do plano de dados. Se não vier no JSON, cai no
    // default BUFFER_SIZE (definido em definitions.h) via o valor padrão do
    // próprio membro em NetworkConfig.
    net_cfg.buffer_size = cfg["network_params"].value("buffer_size_flits", net_cfg.buffer_size);

    // Coeficientes do custo computacional do Dijkstra, em ciclos (mínimo 1
    // ciclo por operação -- ver levantamento de constantes de tempo).
    // Substituem os antigos dijkstra_base_ns_per_node/dijkstra_pq_op_ns/
    // dijkstra_edge_check_ns (fracionários, em ns) e o wait(5,SC_NS) fixo
    // que existia separadamente no ControlUnit (agora é
    // dijkstra_dispatch_cycles, um só lugar de custo algorítmico).
    net_cfg.dijkstra_dispatch_cycles      = cfg["network_params"].value("dijkstra_dispatch_cycles", net_cfg.dijkstra_dispatch_cycles);
    net_cfg.dijkstra_init_cycles_per_node = cfg["network_params"].value("dijkstra_init_cycles_per_node", net_cfg.dijkstra_init_cycles_per_node);
    net_cfg.dijkstra_pq_op_cycles         = cfg["network_params"].value("dijkstra_pq_op_cycles", net_cfg.dijkstra_pq_op_cycles);
    net_cfg.dijkstra_edge_check_cycles    = cfg["network_params"].value("dijkstra_edge_check_cycles", net_cfg.dijkstra_edge_check_cycles);
    net_cfg.dijkstra_pq_base_cycles       = cfg["network_params"].value("dijkstra_pq_base_cycles", net_cfg.dijkstra_pq_base_cycles);
    net_cfg.control_clock_ratio           = cfg["network_params"].value("control_clock_ratio", net_cfg.control_clock_ratio);
    if (!(net_cfg.control_clock_ratio > 0.0)) {
        std::cerr << "ERRO: control_clock_ratio deve ser > 0." << std::endl;
        return 1;
    }
    net_cfg.dijkstra_early_exit           = cfg["network_params"].value("dijkstra_early_exit", net_cfg.dijkstra_early_exit);
    net_cfg.routing_algorithm             = cfg["network_params"].value("routing_algorithm", net_cfg.routing_algorithm);
    if (net_cfg.routing_algorithm != "dijkstra" && net_cfg.routing_algorithm != "bfs" &&
        net_cfg.routing_algorithm != "bfs_free") {
        std::cerr << "ERRO: routing_algorithm invalido '" << net_cfg.routing_algorithm
                  << "' (use dijkstra, bfs ou bfs_free)." << std::endl;
        return 1;
    }

    // Latência de propagação do plano de controle (SDN -> LocalAgent do
    // roteador), em ciclos.
    int control_plane_latency_cycles = cfg["network_params"].value("control_plane_latency_cycles", 0);
    net_cfg.control_plane_latency = CLOCK_PERIOD * control_plane_latency_cycles;

    // Jitter de retry: se não vier do JSON, usa 25% do retry_wait_cycles
    // como default (em vez de 0), para já evitar o "thundering herd"
    // sincronizado por padrão.
    net_cfg.retry_jitter_cycles = cfg["network_params"].value(
        "retry_jitter_cycles", std::max(1, net_cfg.retry_wait_cycles / 4));

    // Latência de arbitragem (round-robin entre ControlUnits), em ciclos.
    net_cfg.arbitro_latency_cycles = cfg["network_params"].value("arbitro_latency_cycles", net_cfg.arbitro_latency_cycles);

    int num_cu = cfg["network_params"]["num_control_units"];

    // --- Bloco opcional "simulation": suporte a réplicas e warm-up ---
    // Todos os campos são opcionais; ausentes -> comportamento antigo (seed
    // fixa 1, sem warm-up, saída em "results.csv").
    //
    // IMPORTANTE sobre réplicas: o SystemC não permite reiniciar o kernel
    // de simulação dentro do mesmo processo (uma vez que sc_start() roda,
    // não dá pra "resetar" e rodar de novo com outra seed no mesmo
    // binário). Réplicas de verdade são feitas rodando este executável
    // várias vezes externamente, cada vez com um "simulation.seed" e
    // "simulation.output_file" diferentes, e agregando os CSVs depois
    // (ver run_replicas.sh).
    json sim_cfg = cfg.value("simulation", json::object());
    net_cfg.master_seed = sim_cfg.value("seed", 1u);
    double warmup_ns = sim_cfg.value("warmup_ns", 0.0);
    std::string output_file = sim_cfg.value("output_file", std::string("results.csv"));

    // Duração da simulação, antes hardcoded (sc_start(10, SC_US), depois
    // mudado manualmente para 15 e recompilado). Agora configurável via
    // simulation.duration_us -- essencial para o sweep de carga e para
    // topologias maiores, onde mais pacotes/nos precisam de mais tempo
    // simulado só para caberem na janela, sem isso a "incompletude" por
    // corte de tempo se mistura com contencao real.
    double duration_us = sim_cfg.value("duration_us", 15.0);

    stats.set_warmup_window(sc_time(warmup_ns, SC_NS));
    stats.set_sim_duration(sc_time(duration_us, SC_US));

    // Topologia
    TopologyManager* tm = new TopologyManager();
    // Reserva da porta de ejecao do destino (ver TopologyManager.h). Padrao: desligado.
    tm->set_reserve_dst(cfg["network_params"].value("reserve_dst_port", true));
    tm->set_reserve_src(cfg["network_params"].value("reserve_src_port", true));
    // ---- trace (opcional) ----
    {
        const auto& np_t = cfg["network_params"];
        if (np_t.contains("trace_flow_ids")) {
            const auto& t = np_t["trace_flow_ids"];
            if (t.is_number_integer()) {
                trace_flow_ids().insert(t.get<int>());
            } else if (t.is_array()) {
                for (const auto& x : t) trace_flow_ids().insert(x.get<int>());
            } else if (t.is_string()) {
                std::string s = t.get<std::string>();
                if (s == "all") {
                    trace_flow_ids().insert(-1);
                } else {
                    std::stringstream ss(s);
                    std::string tok;
                    while (std::getline(ss, tok, ',')) {
                        if (!tok.empty()) trace_flow_ids().insert(std::stoi(tok));
                    }
                }
            }
        }
        if (!trace_flow_ids().empty()) {
            std::string tf = np_t.value("trace_file", std::string("trace_flows.log"));
            trace_out().open(tf, std::ios::out | std::ios::trunc);
        }
    }

    
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
    // Canais de confirmação (ACK): roteador -> SDN, um por roteador.
    std::vector<sc_fifo<int>*> router_to_sdn_ack_fifos(num_nodes);
    
    // Canais entre o Injetor de Tráfego e as Portas Locais dos Roteadores
    std::vector<sc_fifo<Flit>*> ti_to_router_fifos(num_nodes);
    std::vector<sc_fifo<Flit>*> router_to_ti_fifos(num_nodes);

    // Inicializa os canais de comunicação estritos
    for(int i = 0; i < num_nodes; ++i) {
        sdn_to_router_fifos[i] = new sc_fifo<SwitchConfigCmd>(("sdn_2_R" + std::to_string(i)).c_str(), 1000);
        router_to_sdn_ack_fifos[i] = new sc_fifo<int>(("R" + std::to_string(i) + "_2_sdn_ack").c_str(), 1000);
        // FIFOs de DADOS (Flit): usam buffer_size realista, não mais 1000.
        // Antes, com capacidade 1000, um fluxo inteiro (poucas dezenas de
        // flits em geral) nunca enchia o FIFO, então o backpressure do
        // "buffer cheio" simplesmente nunca acontecia.
        ti_to_router_fifos[i]  = new sc_fifo<Flit>(("ti_2_R" + std::to_string(i)).c_str(), net_cfg.buffer_size);
        router_to_ti_fifos[i]  = new sc_fifo<Flit>(("R" + std::to_string(i) + "_2_ti").c_str(), net_cfg.buffer_size);
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
        routers[i]->config_ack(*router_to_sdn_ack_fifos[i]); // Confirma aplicação de volta ao SDN
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
                // Mesma correção: buffer realista em vez de capacidade "infinita" (1000).
                sc_fifo<Flit>* link_fifo = new sc_fifo<Flit>(fifo_name.c_str(), net_cfg.buffer_size);
                fabric_fifos.push_back(link_fifo); 

                // Roteador 'i' envia dados por este canal
                routers[i]->flit_out[p](*link_fifo);

                // Latencia do link proporcional ao comprimento (opcional).
                // Planta fixa W x W (id = y*W + x); comprimento = distancia de Manhattan.
                if (link_reach_tiles_per_cycle > 0.0) {
                    int W = static_cast<int>(std::lround(std::sqrt(static_cast<double>(num_nodes))));
                    if (W < 1) W = 1;
                    static bool warned_grid = false;
                    if (!warned_grid && W * W != num_nodes) {
                        std::cerr << "AVISO: num_nodes=" << num_nodes
                                  << " nao e quadrado perfeito; comprimento dos links assume grade "
                                  << W << "x" << W << std::endl;
                        warned_grid = true;
                    }
                    int len = std::abs(i % W - vizinho % W) + std::abs(i / W - vizinho / W);
                    int mult = std::max(1, static_cast<int>(std::ceil(len / link_reach_tiles_per_cycle - 1e-9)));
                    routers[i]->muxes[p]->link_delay = net_cfg.link_transit_latency * mult;
                }
                
                // Roteador 'vizinho' lê os dados deste canal na sua porta reversa
                int reverse_port = tm->get_port_to_neighbor(vizinho, i);
                routers[vizinho]->flit_in[reverse_port](*link_fifo);
            } else {
                // --- PORTA DE BORDA (SEM VIZINHO): Conecta a canais dummy ---
                // Criamos um canal sem saída para a entrada e outro para a saída
                std::string dummy_in_nm  = "dummy_in_R"  + std::to_string(i) + "_p" + std::to_string(p);
                std::string dummy_out_nm = "dummy_out_R" + std::to_string(i) + "_p" + std::to_string(p);
                
                sc_fifo<Flit>* d_in  = new sc_fifo<Flit>(dummy_in_nm.c_str(), net_cfg.buffer_size);
                sc_fifo<Flit>* d_out = new sc_fifo<Flit>(dummy_out_nm.c_str(), net_cfg.buffer_size);
                
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
    std::string traffic_mode = cfg["traffic"]["mode"]; // "deterministic", "uniform", "bit_reversal" ou "butterfly"
    TrafficInjector* ti = new TrafficInjector("Traffic_Injector", num_nodes, net_cfg, &stats);
    std::string csv_path;
    // Modelo de tempo de injecao (traffic.injection): ver TrafficUtils.h
    InjectionCfg inj;
    {
        json ij = cfg["traffic"].contains("injection") ? cfg["traffic"]["injection"] : json::object();
        inj.mode        = ij.value("mode", std::string("burst"));
        inj.burst_max   = ij.value("burst_max", 4);
        inj.mean_gap_ns = ij.value("mean_gap_ns", 0.0);
        inj.spacing_ns  = ij.value("spacing_ns", 100);
        inj.seed        = ij.value("seed", cfg["traffic"].value("seed", static_cast<int>(net_cfg.master_seed)));
    }

    if(traffic_mode == "deterministic"){
        csv_path = cfg["traffic"]["source_file"];
    } else if (traffic_mode == "uniform"){
        // Se traffic.seed nao for especificado, cai no master_seed da
        // simulacao -- assim, mudar so "simulation.seed" ja basta para
        // gerar uma replica genuinamente diferente (padrao de trafego E
        // jitter de retry mudam juntos), a menos que o usuario queira
        // fixar o trafego e variar so o jitter (setando traffic.seed
        // explicitamente).
        int seed = cfg["traffic"].value("seed", static_cast<int>(net_cfg.master_seed));
        int num_packets = cfg["traffic"].value("num_packets", 1000);
        generateUniformTraffic(num_nodes, num_packets, seed, "uniform.csv", inj);
        csv_path = "uniform.csv";
    } else if (traffic_mode == "bit_reversal"){
        // Padrao de permutacao: exige num_nodes potencia de 2. Reusa o
        // mesmo campo traffic.num_packets do modo uniform, para permitir
        // comparacao com o mesmo volume total de trafego entre padroes.
        int num_packets = cfg["traffic"].value("num_packets", 1000);
        generateBitReversalTraffic(num_nodes, num_packets, "bit_reversal.csv", inj);
        csv_path = "bit_reversal.csv";
    } else if (traffic_mode == "butterfly"){
        // Padrao de permutacao "perfect shuffle" (rotaciona os bits do
        // endereco). Mesma logica de reaproveitamento de num_packets.
        int num_packets = cfg["traffic"].value("num_packets", 1000);
        generateButterflyTraffic(num_nodes, num_packets, "butterfly.csv", inj);
        csv_path = "butterfly.csv";
    }else{
        std::cerr << "Erro: Modo de trafego desconhecido: " << traffic_mode << std::endl;
        return 1;
    }

    ti->load_traffic_from_csv(csv_path);

    // Pré-registra todos os fluxos do tráfego ANTES da simulação começar.
    // Sem isso, fluxos cujo start_time_ns cai depois do fim da janela de
    // sc_start() nunca aparecem no relatório final (nem como incompletos).
    stats.register_expected_flows(ti->traffic_queue);
    
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
    sdn->set_stats(&stats);
    
    sdn->requisitions_in(request_fifo);
    sdn->path_ready_out(path_ready_fifo);
    
    // Bind da entrada de teardown do SDN lendo do FIFO
    sdn->teardown_in(teardown_fifo);

    // Conectando o plano de controle de saída do SDN aos canais dos roteadores
    for(int i = 0; i < num_nodes; ++i) {
        // Presumindo que seu SDN possui um array de portas chamado 'config_out'
        sdn->router_config_out[i](*sdn_to_router_fifos[i]); 
        sdn->router_config_ack_in[i](*router_to_sdn_ack_fifos[i]);
    }
    
    // =========================================================================
    // 6. EXECUÇÃO DA SIMULAÇÃO
    // =========================================================================
    std::cout << "Iniciando a simulacao do sistema..." << std::endl;
    
    sc_start(duration_us, SC_US);
    
    std::cout << "Simulacao finalizada com sucesso." << std::endl;

    stats.generate_report(output_file);

    // Exporta a utilizacao por link (quantos fluxos passaram por cada
    // link fisico ao longo da simulacao) -- usado para confirmar/refutar
    // hipoteses de gargalo/concentracao de trafego em poucos links (ex:
    // atalhos de longo alcance de uma small-world), mesmo quando as
    // metricas estruturais (diametro/caminho medio) parecem boas.
    // Nome derivado de output_file: "results_seed3.csv" ->
    // "results_seed3_linkusage.csv".
    {
        std::string link_usage_file = output_file;
        std::size_t dot_pos = link_usage_file.rfind(".csv");
        if (dot_pos != std::string::npos) {
            link_usage_file = link_usage_file.substr(0, dot_pos) + "_linkusage.csv";
        } else {
            link_usage_file += "_linkusage.csv";
        }
        tm->export_link_usage(link_usage_file);
    }

    // Desalocação segura de memória (Evitando leaks no C++)
    delete tm;
    delete ti;
    delete sdn;
    
    for (auto router : routers) delete router;
    for (auto fifo : sdn_to_router_fifos) delete fifo;
    for (auto fifo : router_to_sdn_ack_fifos) delete fifo;
    for (auto fifo : ti_to_router_fifos) delete fifo;
    for (auto fifo : router_to_ti_fifos) delete fifo;
    for (auto fifo : fabric_fifos) delete fifo;

    return 0;
    
}