#ifndef OUTPUT_MUX_H
#define OUTPUT_MUX_H

#include <systemc.h>
#include "definitions.h"
#include <iostream>

SC_MODULE(OutputMUX) {
    // Portas de entrada: 5 entradas (N, S, E, W, Local)
    sc_fifo_in<Flit> flit_in[NUM_PORTS];

    // Controle vindo do LocalAgent
    sc_in<int> sel;       // Qual índice de porta selecionar
    sc_in<bool> enable;   // Habilita a saída

    // Saída para o link externo
    sc_fifo_out<Flit> flit_out;

    void mux_logic() {
        while (true) {
            // Se o MUX não estiver habilitado pelo SDN, espera uma mudança no controle
            if (!enable.read()) {
                wait(enable.value_changed_event() | sel.value_changed_event());
                continue; 
            }

            int port = sel.read();
            if (port >= 0 && port < NUM_PORTS) {
                // O .read() BLOQUEIA se o buffer de entrada estiver vazio
                Flit f = flit_in[port].read(); 
                
                // O .write() BLOQUEIA automaticamente se o próximo roteador estiver cheio (Backpressure!)
                flit_out.write(f); 
            } else {
                wait(sel.value_changed_event() | enable.value_changed_event());
            }
        }
    }

    SC_CTOR(OutputMUX) {
        SC_THREAD(mux_logic);
    }
    
};

#endif