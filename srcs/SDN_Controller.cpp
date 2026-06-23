#include "SDN_Controller.h"

SDN_Controller::SDN_Controller(sc_module_name name, int num_cus, int num_routers):
    sc_module(name),
    num_cus(num_cus),
    //internal_fifo_to_arb("internal_fifo", 100),
    teardown_in("teardown_in"),
    cu_buses("cu_buses", num_cus),
    internal_ready_buses("ready_buses", num_cus),
    router_config_out("router_config_out", num_routers)
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

void SDN_Controller::configure_path_hardware(const std::vector<int>& route, int flow_id){
    // 1. Salva a rota no mapa para sabermos exatamente o que desativar no Teardown
    active_paths[flow_id] = route;

    // 2. Passa configurando cada roteador do caminho (exceto o destino final, que só recebe)
    for (size_t i = 0; i < route.size(); ++i) {
        int current_node = route[i];
        int next_node    = route[i + 1];

        int prev_node = (i == 0) ? -1 : route[i - 1];

        // 1. Qual porta de SAÍDA do current_node vai para o next_node?
        int out_port;

        if(i == route.size() - 1){
            out_port = PORT_LOCAL;
        }else{
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
                int next_router = route[i+1];

                // Descobre qual porta de entrada e saída foi usada (usando seu TopologyManager)
                int in_port = (i == 0) ? PORT_LOCAL : tm->get_port_to_neighbor(current_router, route[i-1]);
                int out_port;

                if(i == route.size()-1){
                    out_port = PORT_LOCAL;
                }else{
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

            tm->release_path(route);

            // 4. Limpa a rota da memória do controlador para liberar os recursos lógicos
            active_paths.erase(flow_id);
            
            //std::cout << "@" << sc_time_stamp() << " [SDN_Controller] TEARDOWN concluido para o Flow ID " 
            //          << flow_id << ". Recursos liberados." << std::endl;
        }
    }
}