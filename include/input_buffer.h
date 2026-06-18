#ifndef INPUT_BUFFER_H
#define INPUT_BUFFER_H

#include <systemc.h>
#include "definitions.h"

SC_MODULE(InputBuffer) {
    sc_in<bool> clk;
    sc_in<int> target_port;
    sc_fifo_in<Flit>  fifo_in;
    sc_fifo_out<Flit> fifo_out[NUM_PORTS];
    sc_time latency;

    void buffer_logic() {
        while (true) {
            Flit f = fifo_in.read(); // BLOQUEIA se o buffer estiver vazio

            int out_p = target_port.read();

            if (out_p >= 0 && out_p < NUM_PORTS) {
                
                // Simula a latência de processamento
                wait(latency); 
                
                // Envia para o MUX correto na matriz interna
                fifo_out[out_p].write(f); 
                
            } else {
                // Se a rota for inválida, descarta o flit ou exibe um alerta de erro
                std::cout << "@" << sc_time_stamp() << " [Erro InputBuffer] Flit recebido mas rota interna " 
                          << out_p << " é inválida!" << std::endl;
            }
            
        }
    }

    InputBuffer(sc_module_name name, sc_time lat) : sc_module(name), latency(lat) {
        SC_THREAD(buffer_logic);
    }
};

#endif