#ifndef TEST_BACKPRESSURE_H
#define TEST_BACKPRESSURE_H

#include <systemc.h>
#include "Router.h"

SC_MODULE(TestBackpressure) {
    sc_clock clk;
    sc_signal<bool> rst;
    
    sc_signal<Flit> in_data[NUM_PORTS];
    sc_signal<Flit> out_data[NUM_PORTS];
    sc_signal<bool> ready_in[NUM_PORTS]; // Controlamos isso para simular congestionamento
    sc_signal<bool> valid_out[NUM_PORTS];
    sc_signal<int> ort[NUM_PORTS];
    sc_signal<bool> en_ctrl[NUM_PORTS];

    Router* dut;

    void run_test() {
        // 1. Reset
        rst.write(true);
        for(int i=0; i<NUM_PORTS; i++) {
            ready_in[i].write(true); // Inicialmente, todos prontos
            ort[i].write(0);
            en_ctrl[i].write(false);
        }
        wait(20, SC_NS);
        rst.write(false);

        // 2. Setup: EB 0 -> MUX 0
        ort[0].write(0);
        en_ctrl[0].write(true);
        
        // 3. SIMULAÇÃO DE CONGESTIONAMENTO:
        // Bloqueamos a saída (ready_in = false) antes de enviar o dado
        cout << "[BackpressureTest] Bloqueando Saida 0 (ready_in = false)" << endl;
        ready_in[0].write(false); 
        
        Flit f1; f1.id = 505;
        in_data[0].write(f1);
        
        wait(30, SC_NS); // Esperamos 3 ciclos
        
        cout << "[BackpressureTest] Verificando se o dado ainda esta no EB..." << endl;
        // O dado ID 505 deve estar preso no EB 0.
        // O valid_out do roteador (valid_out[0]) DEVE estar baixo, pois o destino não aceitou.
        
        // 4. LIBERAÇÃO:
        cout << "[BackpressureTest] Liberando Saida 0 (ready_in = true)" << endl;
        ready_in[0].write(true);
        
        wait(10, SC_NS);
        Flit empty; empty.id = 0;
        in_data[0].write(empty);
        
        cout << "[BackpressureTest] Teste finalizado." << endl;
        sc_stop();
    }

    SC_CTOR(TestBackpressure) : clk("clk", 10, SC_NS) {
        dut = new Router("Router_DUT");
        dut->clk(clk); dut->rst(rst);
        
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