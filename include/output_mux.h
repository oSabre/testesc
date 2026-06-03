#ifndef OUTPUT_MUX_H
#define OUTPUT_MUX_H

#include <systemc.h>
#include "definitions.h"
#include <iostream>

SC_MODULE(OutputMUX) {
    // 5 entradas vindas dos Elastic Buffers
    int router_id;
    sc_in<bool> rst;
    sc_in_clk clk;
    sc_in<Flit> in_ports[NUM_PORTS]; 
    sc_in<bool> enable;
    // Seleção vinda da ORT (configurada pelo Controller SDN)
    // O valor aqui será o índice do buffer de entrada selecionado (0 a 4)
    sc_in<int> selection; 
    // Saída final
    sc_out<Flit> out;
    // Sinais de handshake
    sc_in<bool> ready_in; // Vem do receptor (próximo hop)
    sc_out<bool> valid_out; // Vai para o receptor
    sc_out<bool> ack_to_eb[NUM_PORTS]; //handshake para o eb
    sc_in<bool> in_valid[NUM_PORTS];
    bool dado_enviado;

    void process() {
        /*
        std::cout << "@" << sc_time_stamp() << " [MUX " << router_id 
          << "] debug: enable=" << enable.read() 
          << " sel=" << selection.read() 
          << " in_valid[0]=" << in_valid[0].read() << std::endl;
        */

        if(rst.read()){
            valid_out.write(false);
            Flit empty; empty.id = 0;
            out.write(empty);
            for(int i = 0; i < NUM_PORTS; ++i) {
                ack_to_eb[i].write(false);
            }
            return;
        }

        if (!enable.read()) {
            valid_out.write(false);
            for(int i = 0; i < NUM_PORTS; ++i) {
                ack_to_eb[i].write(false);
            }
            return;
        }

        int sel = selection.read();
        std::cout << "@" << sc_time_stamp() << " [MUX " << router_id << "] "
                  << "sel=" << sel 
                  << " | in_valid[" << sel << "]=" << (sel >= 0 && sel < NUM_PORTS ? in_valid[sel].read() : -1)
                  << " | ready_in=" << ready_in.read() << std::endl;

        dado_enviado = false;

        if (sel < 0 || sel >= NUM_PORTS) return;

        if (!in_valid[sel].read()) {
            valid_out.write(false);
            for(int i = 0; i < NUM_PORTS; ++i) ack_to_eb[i].write(false);
            dado_enviado = false;
            return; 
        }

        // 3. Lógica de Handshake
        if (in_valid[sel].read() && ready_in.read()) {
            out.write(in_ports[sel].read());
            valid_out.write(true);

            // Roteia o sinal de ACK apenas para o EB selecionado
            for(int i = 0; i < NUM_PORTS; ++i) {
                ack_to_eb[i].write(i == sel);
            }
            dado_enviado = true;
            std::cout << "  -> [MUX " << router_id << "] DADO ENVIADO (ID: " << in_ports[sel].read().id << ")" << std::endl;
        } else if(!ready_in.read()) {
            valid_out.write(false);
            // Reseta todos os ACKs
            for(int i = 0; i < NUM_PORTS; ++i) {
                ack_to_eb[i].write(false);
            }
            dado_enviado = false;
            std::cout << "  -> [MUX " << router_id << "] BLOQUEIO: Receptor não pronto (ready_in=0)" << std::endl;
        }
    }
    
    void monitor_selection() {
        if(selection.event()) {
            std::cout << "@" << sc_time_stamp() << " [MUX " << router_id << "] Nova rota: " << selection.read() << std::endl;
        }
    }

    OutputMUX(sc_module_name name, int _id) : sc_module(name), router_id(_id){
        SC_METHOD(process);
        sensitive << clk.pos();
        sensitive << enable;      // Adicione isto
        sensitive << selection;   // Adicione isto
        sensitive << ready_in;    // Adicione isto
        for(int i=0; i<NUM_PORTS; i++) sensitive << in_valid[i];
        dont_initialize();
    }
};

#endif