#include "SDN_Controller.h"
#include <iostream>
#include <algorithm>

SDN_Controller::SDN_Controller(sc_module_name name, int num_cus, int num_routers):
    sc_module(name),
    num_cus(num_cus),
    //internal_fifo_to_arb("internal_fifo", 100),
    teardown_in("teardown_in"),
    cu_buses("cu_buses", num_cus),
    internal_ready_buses("ready_buses", num_cus),
    router_config_out("router_config_out", num_routers),
    router_config_ack_in("router_config_ack_in", num_routers)
    {
        arb = new Arbitro("arb", num_cus);
        arb->clk(clk);
        arb->requisitions_in(requisitions_in);


        aggregator = new ControlAggregator("aggregator", num_cus);
        aggregator->output(path_ready_out); // Agregador joga na saída do Controller

        cus.init(num_cus);

        for(int i = 0; i < num_cus; i++){
            // Conexão Árbitro -> CU
            arb->cu_request_ports[i](cu_buses[i]);
            cus[i].request_in(cu_buses[i]);
            cus[i].clk(clk);
            cus[i].set_parent(this);

            // Conexão CU -> Agregador (via o canal internal_ready_buses)
            cus[i].path_ready_out(internal_ready_buses[i]);
            aggregator->inputs[i](internal_ready_buses[i]);
        }

        // Uma thread ouvinte de ACK por roteador. Precisa ser uma por
        // roteador (não uma só compartilhada) porque cada uma bloqueia
        // lendo seu próprio FIFO -- uma thread só não conseguiria ouvir
        // N roteadores concorrentemente.
        for(int i = 0; i < num_routers; i++){
            sc_spawn(sc_bind(&SDN_Controller::ack_listener_process, this, i));
        }

        //SC_METHOD(bridge_port_to_fifo);
        //sensitive << clk.pos();
        SC_THREAD(process_teardown);
    }

    /*
void SDN_Controller::bridge_port_to_fifo(){
    if(requisitions_in.event() && internal_fifo_to_arb.num_free() > 0){
        internal_fifo_to_arb.write(requisitions_in.read());
    }
}
    */
void SDN_Controller::set_topology(TopologyManager* _tm){
    tm = _tm;
    for(int i = 0; i < num_cus; i++){
        cus[i].set_topology(_tm);
    }
}

void SDN_Controller::set_config(const NetworkConfig* _cfg) {
    cfg = _cfg;
    for(int i = 0; i < num_cus; i++) {
        cus[i].set_config(_cfg);
    }
}

void SDN_Controller::set_stats(StatsCollector* _stats) {
    stats = _stats;
}

void SDN_Controller::ack_listener_process(int router_index) {
    while (true) {
        // Bloqueia até o LocalAgent deste roteador confirmar a aplicação
        // de algum comando (identificado pelo flow_id que ele mandou).
        int flow_id = router_config_ack_in[router_index].read();

        ack_mutex.lock();
        acked_routers_by_flow[flow_id].insert(router_index);
        ack_mutex.unlock();

        // Acorda qualquer thread parada em wait_for_route_ack esperando
        // por esta (ou outra) confirmação.
        ack_event.notify();
    }
}

void SDN_Controller::wait_for_route_ack(int flow_id, const std::vector<int>& route) {
    std::set<int> needed(route.begin(), route.end());

    while (true) {
        ack_mutex.lock();
        auto it = acked_routers_by_flow.find(flow_id);
        bool all_acked = (it != acked_routers_by_flow.end()) &&
                         std::includes(it->second.begin(), it->second.end(),
                                       needed.begin(), needed.end());
        ack_mutex.unlock();

        if (all_acked) {
            break;
        }

        // Nao ha risco de perder uma notificacao entre o check acima e
        // este wait: acked_routers_by_flow persiste independente de quem
        // esta esperando, entao mesmo que um ACK chegue exatamente entre o
        // unlock e o wait, o proximo ack_event.notify() (de QUALQUER
        // roteador) nos acorda para reavaliar a condicao do zero.
        wait(ack_event);
    }

    // Limpa o estado deste flow_id: a proxima vez que esta funcao for
    // chamada com o mesmo flow_id (ex: agora foi setup, depois sera
    // teardown do MESMO fluxo) deve comecar a contar os ACKs do zero.
    ack_mutex.lock();
    acked_routers_by_flow.erase(flow_id);
    ack_mutex.unlock();
}

void SDN_Controller::report_flow_discarded(int flow_id) {
    std::cerr << "@" << sc_time_stamp() << " [SDN_Controller] Flow " << flow_id
              << " DESCARTADO: excedeu max_retries sem conseguir alocar rota."
              << std::endl;

    if (stats != nullptr) {
        stats->record_discarded(flow_id, sc_time_stamp());
    }
    // Nao ha nada em active_paths para limpar aqui: o descarte acontece
    // ANTES de qualquer rota ter sido efetivamente alocada/configurada
    // (configure_path_hardware so eh chamado apos try_allocate_path ter
    // sucesso), entao nenhum link ficou reservado para este flow.
}

void SDN_Controller::configure_path_hardware(const std::vector<int>& route, int flow_id){
    // 1. Salva a rota no mapa para sabermos exatamente o que desativar no Teardown
    active_paths[flow_id] = route;

    // 2. Passa configurando cada roteador do caminho (exceto o destino final, que só recebe)
    for (size_t i = 0; i < route.size(); ++i) {
        int current_node = route[i];

        int prev_node = (i == 0) ? -1 : route[i - 1];

        // 1. Qual porta de SAÍDA do current_node vai para o next_node?
        // OBS: route[i+1] só existe quando i não é o último índice, então
        // next_node só é lido dentro do else (antes isso acessava
        // route[route.size()], fora dos limites do vetor).
        int out_port;

        if(i == route.size() - 1){
            out_port = PORT_LOCAL;
        }else{
            int next_node = route[i + 1];
            out_port = tm->get_port_to_neighbor(current_node, next_node);
        }

        // 2. Qual porta de ENTRADA do current_node vem do prev_node?
        int in_port = (prev_node == -1) ? PORT_LOCAL : tm->get_port_to_neighbor(current_node, prev_node);

        // Monta o comando
        SwitchConfigCmd cmd;
        cmd.action = SETUP;
        cmd.output_port = out_port; 
        cmd.input_port  = in_port; 
        cmd.enable = true;
        cmd.flow_id = flow_id;

        // 5. Envia pelo "fio" dedicado daquele roteador específico (Graças ao laço/vetor!)
        router_config_out[current_node].write(cmd);

        // Log de validação
        //std::cout << "[SDN] Roteador " << current_node << ": Conectando Entrada " 
        //          << in_port << " -> Saida " << out_port << std::endl;
    }
}

void SDN_Controller::process_teardown() {
    while (true) {
        // 1. Bloqueia até chegar um pedido de teardown do TrafficInjector
        int flow_id = teardown_in.read();

        //std::cout << "@" << sc_time_stamp() << " [SDN_Controller] Iniciando TEARDOWN para o Flow ID " 
        //          << flow_id << std::endl;

        // 2. Verifica se a rota existe no mapa
        if (active_paths.find(flow_id) != active_paths.end()) {
            std::vector<int> route = active_paths[flow_id];

            // 3. Percorre os roteadores da rota (exceto o último, que é o destino final e não repassa)
            for (size_t i = 0; i < route.size(); ++i) {
                int current_router = route[i];

                // Descobre qual porta de entrada e saída foi usada (usando seu TopologyManager)
                int in_port = (i == 0) ? PORT_LOCAL : tm->get_port_to_neighbor(current_router, route[i-1]);
                int out_port;

                if(i == route.size()-1){
                    out_port = PORT_LOCAL;
                }else{
                    // route[i+1] só existe quando i não é o último índice
                    int next_router = route[i+1];
                    out_port = tm->get_port_to_neighbor(current_router, next_router);
                }

                // Monta o comando de liberação (supondo que seu SwitchConfigCmd tenha um campo para isso)
                SwitchConfigCmd cmd;
                cmd.flow_id = flow_id;
                cmd.input_port = in_port;
                cmd.output_port = out_port;
                cmd.action = RELEASE; // FLAG IMPORTANTE: false significa TEARDOWN / Desconectar

                // Envia o comando para o Agente Local do Roteador
                router_config_out[current_router].write(cmd);
                
                //std::cout << "  -> [SDN] Roteador " << current_router 
                //          << ": Desconectando Entrada " << in_port << " da Saida " << out_port << std::endl;
            }  

            // Espera a confirmação real de que todos os roteadores da rota
            // aplicaram o RELEASE (LocalAgent já desligou o mux/buffer),
            // em vez de um "wait" de margem fixa -- que falhava sempre que
            // algum roteador estava com a fila de comandos ocupada. Sem
            // isso, tm->release_path() podia marcar os links como livres
            // ANTES do hardware realmente desconectar, permitindo que um
            // novo fluxo reservasse e usasse esses mesmos links
            // prematuramente.
            wait_for_route_ack(flow_id, route);

            tm->release_path(route);

            // 4. Limpa a rota da memória do controlador para liberar os recursos lógicos
            active_paths.erase(flow_id);
            
            //std::cout << "@" << sc_time_stamp() << " [SDN_Controller] TEARDOWN concluido para o Flow ID " 
            //          << flow_id << ". Recursos liberados." << std::endl;
        }
    }
}