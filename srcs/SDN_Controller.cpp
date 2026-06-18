#include "SDN_Controller.h"

SDN_Controller::SDN_Controller(sc_module_name name, int num_cus, int num_routers):
    sc_module(name),
    num_cus(num_cus),
    //internal_fifo_to_arb("internal_fifo", 100),
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
        sensitive << clk.pos();
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
    for (size_t i = 0; i < route.size() - 1; ++i) {
        int current_node = route[i];
        int next_node    = route[i + 1];

        int prev_node = (i == 0) ? -1 : route[i - 1];

        // 1. Qual porta de SAÍDA do current_node vai para o next_node?
        int out_port = tm->get_port_to_neighbor(current_node, next_node);

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
        std::cout << "[SDN] Roteador " << current_node << ": Conectando Entrada " 
                  << in_port << " -> Saída " << out_port << std::endl;
    }
}