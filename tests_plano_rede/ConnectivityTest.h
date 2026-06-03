#ifndef CONNECTIVITY_TEST_H
#define CONNECTIVITY_TEST_H

#include <systemc.h>
#include "Router.h"

SC_MODULE(ConnectivityTest) {
    sc_clock clk;
    sc_signal<bool> rst;
    
    // Sinais de controle e dados
    sc_signal<Flit> in_data[NUM_PORTS];
    sc_signal<Flit> out_data[NUM_PORTS];
    sc_signal<bool> ready_in[NUM_PORTS];
    sc_signal<bool> valid_out[NUM_PORTS];
    sc_signal<int> ort[NUM_PORTS];
    sc_signal<bool> en_ctrl[NUM_PORTS]; // Sinais de Enable SDN

    Router* dut; 

    void run_test() {
        // 1. Reset Global
        rst.write(true);
        for(int i=0; i<NUM_PORTS; i++) {
            ready_in[i].write(true);
            ort[i].write(0);
            en_ctrl[i].write(false); // Tudo desligado inicialmente
        }
        wait(20, SC_NS);
        rst.write(false);

        // 2. Teste: Rota do Buffer 0 para a Saída 0
        cout << "[ConnectivityTest] Configurando Rota: EB 0 -> MUX 0" << endl;
        ort[0].write(0);          // MUX 0 seleciona EB 0
        en_ctrl[0].write(true);   // Habilita MUX 0
        
        Flit f1; f1.id = 101;
        in_data[0].write(f1);
        wait(10, SC_NS);
        
        // Limpa a entrada após o envio
        Flit empty; empty.id = 0;
        in_data[0].write(empty);

        // 3. Teste: Troca dinâmica para MUX 1 lendo EB 0
        cout << "[ConnectivityTest] Mudando rota para: EB 0 -> MUX 1" << endl;
        wait(10, SC_NS);
        
        // Desativa o MUX anterior e ativa o novo
        en_ctrl[0].write(false); 
        en_ctrl[1].write(true);
        ort[1].write(0);          // MUX 1 agora seleciona EB 0
        
        Flit f2; f2.id = 202;
        in_data[0].write(f2);     // Envia novo dado para o mesmo EB 0
        wait(10, SC_NS);

        in_data[0].write(empty);
        wait(50, SC_NS);
        cout << "[ConnectivityTest] Fim da simulacao." << endl;
        cout << endl;
        sc_stop();
    }

    
    void monitor() {
        static int last_id[NUM_PORTS] = {0, 0, 0, 0, 0};
        for(int i=0; i<NUM_PORTS; i++) {
            Flit f = out_data[i].read();
            if(f.id != 0 && f.id != last_id[i]) {
                cout << "@" << sc_time_stamp() << " Dado recebido na Saida " << i 
                     << " ID: " << f.id << endl;
                last_id[i] = f.id;
            }
        }
    }

    SC_CTOR(ConnectivityTest) : clk("clk", 10, SC_NS) {
        dut = new Router("Router_DUT");
        dut->clk(clk);
        dut->rst(rst);
        
        for(int i=0; i<NUM_PORTS; i++) {
            dut->in_ports[i](in_data[i]);
            dut->out_ports[i](out_data[i]);
            dut->ready_in[i](ready_in[i]);
            dut->valid_out[i](valid_out[i]);
            dut->ort_table[i](ort[i]);
            dut->mux_enable_ctrl[i](en_ctrl[i]); // Conexão do Enable SDN
        }

        SC_THREAD(run_test);
        SC_METHOD(monitor);
        sensitive << clk.posedge_event();
    }
};

#endif