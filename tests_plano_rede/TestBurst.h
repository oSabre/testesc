#ifndef TEST_BURST_H
#define TEST_BURST_H

#include <systemc.h>
#include "Router.h"

SC_MODULE(TestBurst) {
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
            ort[i].write(0);
            en_ctrl[i].write(true);
            Flit f_zero; f_zero.id = 0;
            in_data[i].write(f_zero);
        }
        wait(20, SC_NS);
        rst.write(false);
        wait(10, SC_NS); // Garante alinhamento com o clock

        int burst_size = 50; 
        cout << "[BurstTest] Iniciando rajada de " << burst_size << " flits..." << endl;

        for (int i = 1; i <= burst_size; i++) {
            // 1. Aguarda estar pronto
            while(!ready_in[0].read()) {
                wait(clk.period());
            }

            // 2. Envia o dado EXATAMENTE antes da subida do clock
            Flit f;
            f.id = i;
            in_data[0].write(f);
            
            // 3. Espera 1 ciclo de clock para o DUT consumir
            wait(20, SC_NS);
            
            // 4. Aqui não precisamos enviar f_empty imediatamente. 
            // Apenas mantemos o barramento estável para o próximo dado.
        }

        // Finaliza enviando um 0 para indicar que não há mais dados
        Flit f_empty; f_empty.id = 0;
        in_data[0].write(f_empty);

        cout << "[BurstTest] Fim do envio. Aguardando processamento final..." << endl;
        wait(100, SC_NS);
        sc_stop();
    }

    SC_CTOR(TestBurst) : clk("clk", 10, SC_NS) {
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