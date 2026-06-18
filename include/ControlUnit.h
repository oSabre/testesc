#ifndef CONTROL_UNIT_H
#define CONTROL_UNIT_H

#include "TopologyManager.h"
#include "definitions.h"
#include <vector>
#include <queue>
#include <limits>
#include <algorithm>
#include <iostream>
#include <systemc.h>
#include <stats.h>
#include "routingStrategy.h"
#include "SDN_Controller.h"

SC_MODULE(ControlUnit) {
    sc_in_clk clk;
    sc_fifo_in<PacketMetadata> request_in;

    sc_fifo_out<int> path_ready_out;

    TopologyManager* tm;
    const NetworkConfig* cfg;
    SDN_Controller* parent_sdn;

    ControlUnit(sc_module_name name);
    void process_routing();

    void set_topology(TopologyManager* _tm);
    void set_config(const NetworkConfig* _cfg);
    void set_parent(SDN_Controller* sdn);

    std::vector<int> calculate_dijkstra(int src, int dst);
};

#endif