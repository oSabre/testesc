#ifndef SDN_CONTROLLER_H
#define SDN_CONTROLLER_H

#include <systemc.h>
#include <vector>
#include "arbitro.h"
#include "definitions.h"
#include "ControlUnit.h"
#include "TopologyManager.h"
#include "ControlAggregator.h"



SC_MODULE(SDN_Controller) {
    int num_cus;
    sc_in_clk clk;
    
    sc_fifo_in<PacketMetadata> requisitions_in;

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

    SDN_Controller(sc_module_name name, int num_cus, int num_routers);
    //void bridge_port_to_fifo();
    void set_topology(TopologyManager* _tm);
    void set_config(const NetworkConfig* _cfg);
    void configure_path_hardware(const std::vector<int>& route, int flow_id);

};
#endif