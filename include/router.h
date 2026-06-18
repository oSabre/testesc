#ifndef ROUTER_H
#define ROUTER_H

#include <systemc.h>
#include "definitions.h"
#include "input_buffer.h"
#include "OutputMUX.h"
#include "LocalAgent.h"

SC_MODULE(Router) {
    // Portas externas do Roteador
    sc_in<bool> clk;
    sc_fifo_in<Flit> flit_in[NUM_PORTS];
    sc_fifo_out<Flit> flit_out[NUM_PORTS];
    sc_fifo_in<SwitchConfigCmd> config_in;

    // Sinais internos (Fios de cobre do Roteador)
    sc_fifo<Flit> buffered_flit[NUM_PORTS]; // Fio: Buffer -> Mux
    sc_signal<int> mux_sel[NUM_PORTS];        // Fio: Agent -> Mux (Seleção)
    sc_signal<bool> mux_enable[NUM_PORTS];    // Fio: Agent -> Mux (Liga/Desliga)
    sc_fifo<Flit> input_channels[NUM_PORTS];

    // Submódulos
    LocalAgent* agent;
    InputBuffer* buffers[NUM_PORTS];
    OutputMUX* muxes[NUM_PORTS];
    
    SC_CTOR(Router) {
        // 1. Instancia o Agente Local
        agent = new LocalAgent("agent");
        agent->config_in(config_in); // Conecta o fifo de configuração

        // 2. Instancia e Conecta os Buffers e MUXes
        for (int i = 0; i < NUM_PORTS; ++i) {
            // Buffer de entrada i
            buffers[i] = new InputBuffer(("buffer_" + std::to_string(i)).c_str(), LAT);
            buffers[i]->clk(clk);
            buffers[i]->fifo_in(input_channels[i]);
            buffers[i]->fifo_out(buffered_flit[i]); // Saída do buffer vira fio interno

            // MUX de saída i
            muxes[i] = new OutputMUX(("mux_" + std::to_string(i)).c_str());
            muxes[i]->sel(mux_sel[i]);
            muxes[i]->enable(mux_enable[i]);
            muxes[i]->flit_out(flit_out[i]); // Saída do MUX vai para a porta externa do roteador

            // Conecta as saídas de TODOS os buffers às entradas DESTE MUX
            for (int j = 0; j < NUM_PORTS; ++j) {
                muxes[i]->flit_in[j](buffered_flit[j]);
            }

            // Conecta o Agente aos sinais de controle deste MUX
            agent->mux_sel[i](mux_sel[i]);
            agent->mux_enable[i](mux_enable[i]);
        }
    }

    // Boa prática: Destruir os componentes ao terminar a simulação
    ~Router() {
        delete agent;
        for (int i = 0; i < NUM_PORTS; ++i) {
            delete buffers[i];
            delete muxes[i];
        }
    }

};

#endif