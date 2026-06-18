#include <systemc.h>
#include "definitions.h"

SC_MODULE(LocalAgent) {
    sc_fifo_in<SwitchConfigCmd> config_in;
    
    // Pinos de saída para os MUXes
    sc_out<int> mux_sel[NUM_PORTS];
    sc_out<bool> mux_enable[NUM_PORTS];

    void agent_thread() {
        while(true) {
            SwitchConfigCmd cmd = config_in.read();

            // Validação de segurança
            if (cmd.output_port >= 0 && cmd.output_port < NUM_PORTS) {
                if (cmd.action == SETUP) {
                    // Configura o MUX da porta de saída correspondente
                    mux_sel[cmd.output_port].write(cmd.input_port);
                    mux_enable[cmd.output_port].write(true);
                    
                    std::cout << "@" << sc_time_stamp() << " [LocalAgent] "
                              << "Executando SETUP: Saída " << cmd.output_port 
                              << " conectada à Entrada " << cmd.input_port << std::endl;
                }else if (cmd.action == RELEASE) {
                    // Desliga o MUX da porta de saída correspondente
                    mux_enable[cmd.output_port].write(false);
                    
                    std::cout << "@" << sc_time_stamp() << " [LocalAgent] "
                              << "Executando RELEASE na Saída " << cmd.output_port << std::endl;
                }
            }
        }
    }

    SC_CTOR(LocalAgent) {
        SC_THREAD(agent_thread);
    }
};