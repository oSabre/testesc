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
    // Confirma ao SDN_Controller que o comando de config_in foi realmente
    // aplicado (não só recebido) -- ver LocalAgent.h para o porquê.
    sc_fifo_out<int> config_ack;

    // Fios de controle do LocalAgent para os MUXes e Buffers
    sc_signal<int> mux_sel[NUM_PORTS];        // Agent -> Mux (Seleção)
    sc_signal<bool> mux_enable[NUM_PORTS];    // Agent -> Mux (Liga/Desliga)
    sc_signal<int> buffer_target[NUM_PORTS];  // Agent -> Buffer (Define o MUX de destino)

    // Canais e Sinais internos (A infraestrutura interna do Roteador)
    //sc_fifo<Flit> input_channels[NUM_PORTS]; // Ponte entre flit_in externo e o InputBuffer

    // MATRIZ CROSSBAR: Canais de FIFOs independentes entre os Buffers e os MUXes
    // Linha [i] = Buffer de Origem | Coluna [j] = MUX de Destino
    sc_fifo<Flit> crossbar[NUM_PORTS][NUM_PORTS];

    // Submódulos
    LocalAgent* agent;
    InputBuffer* buffers[NUM_PORTS];
    OutputMUX* muxes[NUM_PORTS];
    
    Router(sc_module_name name, const NetworkConfig& net_cfg) : sc_module(name) {
        // 1. Instancia o Agente Local
        agent = new LocalAgent("agent", net_cfg.control_plane_latency);
        agent->config_in(config_in); // Conecta o fifo de configuração
        agent->config_ack(config_ack); // Conecta o fifo de confirmação

        // 2. INSTANCIAÇÃO: Cria todos os buffers e muxes primeiro
        for (int i = 0; i < NUM_PORTS; ++i) {
            buffers[i] = new InputBuffer(("buffer_" + std::to_string(i)).c_str(), LAT);
            muxes[i] = new OutputMUX(("mux_" + std::to_string(i)).c_str(), net_cfg.link_transit_latency);
        }

        // 3. CONEXÃO LINEAR: Conecta portas externas e sinais de controle individuais
        for (int i = 0; i < NUM_PORTS; ++i) {
            // Entrada Externa -> Canal Interno -> InputBuffer
            //flit_in[i](input_channels[i]);
            buffers[i]->clk(clk);
            //buffers[i]->fifo_in(input_channels[i]);
            buffers[i]->fifo_in(flit_in[i]);

            // Controle do Agente indo para o InputBuffer
            buffers[i]->target_port(buffer_target[i]);
            agent->buffer_target[i](buffer_target[i]); 

            // OutputMUX -> Saída Externa
            muxes[i]->flit_out(flit_out[i]);

            // Controle do Agente indo para o OutputMUX
            muxes[i]->sel(mux_sel[i]);
            muxes[i]->enable(mux_enable[i]);
            agent->mux_sel[i](mux_sel[i]);
            agent->mux_enable[i](mux_enable[i]);
        }

        // 4. CONEXÃO DA MALHA (CROSSBAR): Interconecta a matriz de FIFOs
        for (int i = 0; i < NUM_PORTS; ++i) {       // Para cada Buffer i
            for (int j = 0; j < NUM_PORTS; ++j) {   // Para cada MUX j
                // A saída 'j' do Buffer 'i' se conecta ao canal crossbar[i][j]
                buffers[i]->fifo_out[j](crossbar[i][j]);
                
                // A entrada 'i' do MUX 'j' lê do mesmo canal crossbar[i][j]
                muxes[j]->flit_in[i](crossbar[i][j]);
            }
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