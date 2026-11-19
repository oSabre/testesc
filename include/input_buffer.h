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
    int current_target;

    void buffer_logic() {
        current_target = -1;
        while (true) {
            // 2. Bloqueia aguardando um flit
            Flit f = fifo_in.read();

            current_target = target_port.read();
            TRACE_FLOW(f.flow_id, "[InputBuffer " << name() << "] flit " << f.flit_id << " pkt " << f.packet_id << " flow " << f.flow_id << " alvo=" << current_target << (current_target < 0 ? "  !! ROTA NAO CONFIGURADA" : ""));


            //if(f.is_tail) std::cout << "@" << sc_time_stamp() << " [InputBuffer " << name() << "] is tail" << endl;

            //std::cout << "@" << sc_time_stamp() << " [InputBuffer " << name() 
            //              << "] Flit " << f.flit_id << " lendo rota " 
            //              << current_target << std::endl;

            // 3. Encaminha baseado no estado atual
            if (current_target >= 0 && current_target < NUM_PORTS) {
                wait(latency);
                fifo_out[current_target].write(f);
            } else {
                std::cout << "@" << sc_time_stamp() << " [InputBuffer " << name() 
                          << "] ERRO: Flit " << f.flit_id << " chegou, mas rota eh " 
                          << current_target << " (nao configurada!)" << std::endl;
            }
        }
    }

    InputBuffer(sc_module_name name, sc_time lat) : sc_module(name), latency(lat) {
        SC_THREAD(buffer_logic);
    }
};

#endif