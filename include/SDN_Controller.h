#ifndef SDN_CONTROLLER_H
#define SDN_CONTROLLER_H

#include <systemc.h>
#include <vector>
#include "arbitro.h"
#include "definitions.h"
#include "ControlUnit.h"



SC_MODULE(SDN_Controller) {
    sc_in_clk clk;
    
    sc_in<PacketMetadata> requisitions_in;

    // Conexões Internas
    sc_fifo<PacketMetadata> internal_fifo_to_arb;
    // Vetor de FIFOs que ligam o árbitro ás CUs.
    sc_vector<sc_fifo<PacketMetadata>> cu_buses;

    int num_cus;

    Arbitro* arb;
    sc_vector<ControlUnit*> cus;

    SDN_Controller(sc_module_name name, int num_cus);
    void bridge_port_to_fifo();

};
#endif