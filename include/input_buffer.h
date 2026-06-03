#ifndef INPUT_BUFFER_H
#define INPUT_BUFFER_H

#include <systemc.h>
#include "definitions.h"

SC_MODULE(InputBuffer) {
    sc_in_clk clk;
    sc_fifo_in<Flit> in;
    sc_fifo_out<Flit> out;

    void buffer_logic() {
        while(true) {
            wait(); // Sincronizado com o clock
            if (in.num_available() > 0) {
                Flit f = in.read();
                out.write(f); // Passa para o Crossbar
            }
        }
    }

    SC_CTOR(InputBuffer) {
        SC_CTHREAD(buffer_logic, clk.pos());
    }
};

#endif