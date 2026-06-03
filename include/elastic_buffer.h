#ifndef ELASTIC_BUFFER_H
#define ELASTIC_BUFFER_H

#include <systemc.h>
#include "definitions.h"

SC_MODULE(ElasticBuffer) {
    sc_in_clk clk;
    sc_in<bool> rst;
    sc_in<Flit> in;
    sc_out<Flit> out;
    // Sinais de controle de fluxo
    sc_in<bool> ack_in[NUM_PORTS];  // Vem do MUX: "O receptor aceitou o dado?"
    sc_in<bool> valid_in;
    sc_out<bool> valid_out; // Vai para o MUX: "Tenho um dado retido aqui"
    sc_out<bool> ready_out;
    // Registrador interno (a memória do buffer)
    Flit buffer_reg;
    bool full; // Indica se há dado retido

    void eb_logic() {
        if (rst.read()) {
            full = false;
            buffer_reg.id = 0;
            Flit empty; empty.id = 0;
            out.write(empty);
            valid_out.write(false);
            ready_out.write(true);
            return;
        } 

        bool any_ack = false;
        for(int i=0; i<NUM_PORTS; i++){
            if(ack_in[i].read()){
                any_ack = true;
                std::cout << "@" << sc_time_stamp() << " [EB " << name() << "] ACK recebido do MUX " << i << std::endl;
            }
        }

        // 1. Se o buffer está cheio e o receptor (MUX) consumiu o dado
        if (full && any_ack) {
            std::cout << "@" << sc_time_stamp() << " [EB " << name() 
                      << "] Consumiu dado ID " << buffer_reg.id 
                      << " (ACK recebido)" << std::endl;
            full = false;
            buffer_reg.id = 0;

            Flit empty; empty.id = 0;
            out.write(empty);
            valid_out.write(false);
            //return;
        }

        if (!full && valid_in.read()) {
            Flit current_in = in.read();
            if (current_in.id != 0) {
                buffer_reg = current_in;
                full = true;
                out.write(buffer_reg);
                //valid_out.write(true);
                std::cout << "@" << sc_time_stamp() << " [EB] Dado ID " << current_in.id << " capturado." << std::endl;
            }
        }

        /*
        if (clk.event() && clk.read() == 1) {
            Flit current_in = in.read();
            
            // Log de tentativa de recepção
            if (current_in.id != 0 && current_in.id != buffer_reg.id) {
                std::cout << "@" << sc_time_stamp() << " [EB " << name() 
                          << "] Tentando receber ID " << current_in.id 
                          << " | Full=" << full << std::endl;
            }

            if (!full && valid_in.read() && current_in.id != 0 && current_in.id != buffer_reg.id) {
                std::cout << "@" << sc_time_stamp() << " [EB " << name() 
                          << "] SUCESSO: Recebeu e travou dado ID " << current_in.id << std::endl;
                
                buffer_reg = current_in;
                full = true;
                out.write(buffer_reg);
                valid_out.write(true);
            } else if (full && current_in.id != 0 && current_in.id != buffer_reg.id) {
                std::cout << "@" << sc_time_stamp() << " [EB " << name() 
                          << "] ERRO: Buffer cheio, nao pode receber novo dado ID " << current_in.id << std::endl;
            }
        }
            */
        /*
        if (clk.event() && clk.read() == 1 && in.read().id != buffer_reg.id) { 
            std::cout << "DEBUG EB: Recebido ID " << in.read().id << std::endl;
            if (!full && in.read().id != 0) {
                cout << "@" << sc_time_stamp() << " EB " << name() << " recebeu novo dado ID " << in.read().id << endl;
                buffer_reg = in.read();
                full = true;
                out.write(buffer_reg);
                valid_out.write(true);
            }
        }
        */
        valid_out.write(full);
        ready_out.write(!full);
    }

    SC_CTOR(ElasticBuffer) {
        SC_METHOD(eb_logic);
        sensitive << clk.pos();
        for(int i=0; i<NUM_PORTS; i++) sensitive << ack_in[i];
        full = false;
        buffer_reg.id = 0;
    }
};

#endif