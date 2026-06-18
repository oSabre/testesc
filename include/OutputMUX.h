#ifndef OUTPUT_MUX_H
#define OUTPUT_MUX_H

#include <systemc.h>
#include "definitions.h"
#include <iostream>

SC_MODULE(OutputMUX) {
    // Portas de entrada: 5 entradas (N, S, E, W, Local)
    sc_in<Flit> flit_in[NUM_PORTS];

    // Controle vindo do LocalAgent
    sc_in<int> sel;       // Qual índice de porta selecionar
    sc_in<bool> enable;   // Habilita a saída

    // Saída para o link externo
    sc_out<Flit> flit_out;

    void mux_logic() {
        if (enable.read()) {
            int port = sel.read();
            if (port >= 0 && port < NUM_PORTS) {
                flit_out.write(flit_in[port].read());
                return;
            }
        }
        // Se desabilitado ou porta inválida, envia um flit "vazio"
        Flit empty_flit;
        empty_flit.valid = false;
        flit_out.write(empty_flit);
    }

    SC_CTOR(OutputMUX) {
        SC_METHOD(mux_logic);
        // Sensível a qualquer mudança nas entradas ou no controle
        sensitive << enable << sel;
        for(int i = 0; i < NUM_PORTS; ++i) {
            sensitive << flit_in[i];
        }
    }
    
};

#endif