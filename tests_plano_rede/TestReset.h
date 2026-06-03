#ifndef TEST_RESET_H
#define TEST_RESET_H

#include <systemc.h>
#include "Router.h"

SC_MODULE(TestReset) {
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
        // Inicialização
        rst.write(false);
        for(int i=0; i<NUM_PORTS; i++) {
            ready_in[i].write(true);
            ort[i].write(0);
            en_ctrl[i].write(true);
        }
        wait(20, SC_NS);

        // 1. Enviar dado que seria processado
        cout << "[ResetTest] Enviando dado 999..." << endl;
        Flit f; f.id = 999;
        in_data[0].write(f);
        
        // 2. Resetar NO MEIO do caminho (antes de consumir)
        wait(5, SC_NS);
        cout << "[ResetTest] Reset ativado! (Deveria descartar o 999)" << endl;
        rst.write(true);
        
        wait(20, SC_NS);
        
        // 3. Verificar estado
        cout << "[ResetTest] Liberando Reset..." << endl;
        rst.write(false);
        
        // Se o Reset funcionou, o dado 999 não deve ter aparecido na saída
        if(valid_out[0].read() == false) {
            cout << "[ResetTest] Sucesso: Dado descartado e sistema limpo." << endl;
        } else {
            cout << "[ResetTest] FALHA: Dado 999 sobreviveu ao reset!" << endl;
        }

        sc_stop();
    }

    SC_CTOR(TestReset) : clk("clk", 10, SC_NS) {
        dut = new Router("Router_DUT");
        dut->clk(clk); dut->rst(rst);
        // ... (conexões das portas como nos outros testes)
        for(int i=0; i<NUM_PORTS; i++) {
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