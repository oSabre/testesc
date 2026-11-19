#ifndef ARBITRO_H
#define ARBITRO_H

#include <systemc.h>
#include <vector>
#include "definitions.h"
#include "ControlUnit.h"

SC_MODULE(Arbitro) {
    // Portas
    sc_in_clk clk;

    sc_fifo_in<PacketMetadata> requisitions_in;
    
    int num_cus;
    int next_cu;

    // Ponteiro de configuração, para acessar arbitro_latency_cycles.
    // Setado via set_config antes de sc_start(); default nullptr protegido
    // com fallback de 1 ciclo caso, por algum motivo, nunca seja setado.
    const NetworkConfig* cfg = nullptr;

    sc_vector<sc_fifo_out<PacketMetadata>> cu_request_ports;

    Arbitro(sc_module_name name, int num_cus);
    void arbitrate_test_process();
    void arbitrate_process();
    void set_config(const NetworkConfig* _cfg);
};

#endif