#ifndef CROSSBAR_H
#define CROSSBAR_H

#include <systemc.h>
#include "definitions.h"

SC_MODULE(Crossbar) {
    sc_in<Flit> buffer_inputs[NUM_PORTS];
    sc_out<Flit> link_outputs[NUM_PORTS];
    sc_in<int> routing_table[NUM_PORTS]; // SDN: Qual entrada vai para qual saída

    void crossbar_logic() {
        // Lógica de MUX: roteia com base na tabela SDN
        for(int i = 0; i < NUM_PORTS; ++i) {
            int input_src = routing_table[i].read();
            if(input_src != -1 && buffer_inputs[input_src].event()) {
                link_outputs[i].write(buffer_inputs[input_src].read());
            }
        }
    }

    SC_CTOR(Crossbar) {
        SC_METHOD(crossbar_logic);
        for(int i = 0; i < NUM_PORTS; ++i) {
            sensitive << buffer_inputs[i] << routing_table[i];
        }
    }
};

#endif