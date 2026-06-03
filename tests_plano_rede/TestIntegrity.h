#ifndef TEST_INTEGRITY_H
#define TEST_INTEGRITY_H

#include <systemc.h>
#include "Router.h"
#include <iostream>
#include <iomanip> // Para formatar a saída em hex

SC_MODULE(TestIntegrity) {
    sc_clock clk;
    sc_signal<bool> rst;
    sc_signal<Flit> in_data[NUM_PORTS];
    sc_signal<Flit> out_data[NUM_PORTS];
    sc_signal<bool> ready_in[NUM_PORTS];
    sc_signal<bool> valid_out[NUM_PORTS];
    sc_signal<int> ort[NUM_PORTS];
    sc_signal<bool> en_ctrl[NUM_PORTS];

    Router* dut;

    void run_test() {
        // Reset inicial
        rst.write(true);
        for(int i = 0; i < NUM_PORTS; i++) {
            ready_in[i].write(true);
            ort[i].write(0); // Rota fixa para saída 0
            en_ctrl[i].write(true);
            Flit f_zero; f_zero.id = 0;
            in_data[i].write(f_zero);
        }
        wait(20, SC_NS);
        rst.write(false);
        wait(10, SC_NS);

        // Padrões para testar integridade de bits
        unsigned short patterns[] = {0x0000, 0xFFFF, 0xAAAA, 0x5555, 0x3333, 0xCCCC};
        int num_patterns = 6;

        cout << "[IntegrityTest] Iniciando verificacao de integridade de bits..." << endl;

        for (int i = 0; i < num_patterns; i++) {
            Flit f_in;
            f_in.id = patterns[i];
            
            // Envia o dado
            in_data[0].write(f_in);
            
            // Aguarda tempo de processamento do roteador (baseado nos 2 ciclos validados)
            wait(20, SC_NS);
            
            // Verifica se o dado na saída corresponde ao da entrada
            Flit f_out = out_data[0].read();
            
            cout << "[IntegrityTest] Padrao: 0x" << std::hex << std::uppercase << patterns[i] 
                    << " | Recebido: 0x" << f_out.id << std::dec << endl;

            if (f_out.id != patterns[i]) {
                cout << "!!! ERRO: Corrupcao de dados detectada no padrao 0x" << hex << patterns[i] << endl;
                sc_stop();
            }
        }

        cout << "[IntegrityTest] Sucesso! Nenhuma corrupcao de bits detectada." << endl;
        sc_stop();
    }

    SC_CTOR(TestIntegrity) : clk("clk", 10, SC_NS) {
        dut = new Router("Router_DUT");
        dut->clk(clk); dut->rst(rst);
        for(int i = 0; i < NUM_PORTS; i++) {
            dut->in_ports[i](in_data[i]);
            dut->out_ports[i](out_data[i]);
            dut->ready_in[i](ready_in[i]);
            dut->valid_out[i](valid_out[i]);
            dut->ort_table[i](ort[i]);
            dut->mux_enable_ctrl[i](en_ctrl[i]);
        }
        SC_THREAD(run_test);
    }
};

#endif