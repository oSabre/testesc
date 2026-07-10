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

    sc_time link_delay;

    void mux_logic() {
        while (true) {
            // Se o MUX não estiver habilitado pelo SDN, espera uma mudança no controle
            if (!enable.read()) {
                wait(enable.value_changed_event() | sel.value_changed_event());
                continue; 
            }

            int port = sel.read();
            if (port < 0 || port >= NUM_PORTS) {
                wait(sel.value_changed_event() | enable.value_changed_event());
                continue;
            }

            // IMPORTANTE: não podemos usar flit_in[port].read() diretamente aqui,
            // pois ele BLOQUEIA a thread até chegar um flit naquela porta especifica.
            // Se um RELEASE (ou um novo SETUP apontando para outra porta) acontecer
            // enquanto estamos travados nesse read(), a thread nunca acorda, porque
            // sc_signal::write() não interrompe uma leitura bloqueante de sc_fifo.
            // Isso deixava o MUX morto para sempre assim que a rota fosse reconfigurada
            // com uma porta de entrada diferente da anterior.
            //
            // Solução: esperar por dado disponível OU por mudança de config,
            // e só então fazer um nb_read() (que não bloqueia, pois já garantimos
            // que há dado disponível).
            bool reconfigured = false;
            while (flit_in[port].num_available() == 0) {
                wait(flit_in[port].data_written_event()
                     | enable.value_changed_event()
                     | sel.value_changed_event());

                // A config mudou (RELEASE ou novo SETUP para outra porta/entrada):
                // abandona a espera por essa porta e reavalia tudo no topo do loop.
                if (!enable.read() || sel.read() != port) {
                    reconfigured = true;
                    break;
                }
            }

            if (reconfigured) {
                continue;
            }

            Flit f;
            flit_in[port].nb_read(f); // Garantido não bloquear: já sabemos que há dado

            //std::cout << "@" << sc_time_stamp() << " [Output MUX " << name() 
            //          << "] Flit " << f.flit_id << std::endl;
            
            wait(link_delay);
            // O .write() BLOQUEIA automaticamente se o próximo roteador estiver cheio (Backpressure!)
            flit_out.write(f); 
        }
    }

    OutputMUX(sc_module_name name, sc_time delay) : sc_module(name), link_delay(delay) {
        SC_THREAD(mux_logic);
    }
    
};

#endif