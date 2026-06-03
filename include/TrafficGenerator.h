#ifndef TRAFFIC_GENERATOR_H
#define TRAFFIC_GENERATOR_H

#include <systemc.h>
#include "definitions.h"

SC_MODULE(TrafficGenerator) {
    // Porta de saída para o FIFO do Arbitro
    sc_fifo_out<PacketMetadata> out_fifo;
    sc_in_clk clk;
    sc_time taxa_injecao;

    bool mode_deadlock;

    void generate_process() {
        // Aguarda um ciclo para garantir que o sistema inicializou
        wait();

        int packet_count = 0;
        while (true) {
            // Cria um pacote de teste
            PacketMetadata p;
            Stats::add_gerado();

            if(mode_deadlock){
                p.sender_id = (packet_count % 2); 
                p.receiver_id = 1 - (packet_count % 2);
            }else{
                p.sender_id = (packet_count % 4);      // Alterna src entre 0-4
                p.receiver_id = ((packet_count + 1) % 4); // Alterna dst entre 0-4
            }
            
            p.total_flits = 10;
            p.flow_id = packet_count + 1000;

            // Envia para o FIFO
            out_fifo.write(p);
            
            std::cout << "@" << sc_time_stamp() << " [" << name() << "] Disparando..." << std::endl;
            std::cout << "@" << sc_time_stamp() << " [TrafficGenerator] " 
                      << (mode_deadlock ? "DEADLOCK MODE" : "NORMAL MODE") 
                      << " Pacote #" << packet_count << " enviado: " << p << std::endl;

            packet_count++;

            // Espera alguns ciclos antes de enviar o próximo
            wait(taxa_injecao); 
        }
    }

    TrafficGenerator(sc_module_name name, bool deadlock_mode = false, sc_time taxa = sc_time(20, SC_NS)) 
        : sc_module(name), taxa_injecao(taxa), mode_deadlock(deadlock_mode) {
        SC_THREAD(generate_process);
        sensitive << clk.pos();
    }
};

#endif