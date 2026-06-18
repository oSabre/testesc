#ifndef INPUT_BUFFER_H
#define INPUT_BUFFER_H

#include <systemc.h>
#include "definitions.h"

SC_MODULE(InputBuffer) {
    sc_in<bool> clk;
    sc_fifo_in<Flit>  fifo_in;
    sc_fifo_out<Flit> fifo_out;
    sc_time latency;

    void buffer_logic() {
        while (true) {
            Flit f = fifo_in.read(); // BLOQUEIA se o buffer estiver vazio
            
            // Simula a latência de trânsito ou processamento do buffer
            wait(latency); 
            
            fifo_out.write(f);       // BLOQUEIA se o próximo estágio (MUX) estiver cheio
        }
    }

    InputBuffer(sc_module_name name, sc_time lat) : sc_module(name), latency(lat) {
        SC_THREAD(buffer_logic);
    }
};

#endif