#include <systemc.h>
#include "definitions.h"

SC_MODULE(LocalAgent) {
    sc_fifo_in<SwitchConfigCmd> config_in;
    
    // Pinos de saída para os MUXes
    sc_out<int> mux_sel[NUM_PORTS];
    sc_out<bool> mux_enable[NUM_PORTS];
    sc_out<int> buffer_target[NUM_PORTS];

    void agent_thread() {
        while(true) {
            SwitchConfigCmd cmd = config_in.read();

            // Validação de segurança
            if (cmd.output_port >= 0 && cmd.output_port < NUM_PORTS &&
                cmd.input_port >= 0 && cmd.input_port < NUM_PORTS) {
                if (cmd.action == SETUP) {
                    // Configura o MUX da porta de saída correspondente
                    mux_sel[cmd.output_port].write(cmd.input_port);
                    mux_enable[cmd.output_port].write(true);
                    buffer_target[cmd.input_port].write(cmd.output_port);
                    
                    std::cout << "@" << sc_time_stamp() << " [LocalAgent] "
                              << "Executando SETUP: Saida " << cmd.output_port 
                              << " conectada a Entrada " << cmd.input_port << std::endl;
                }else if (cmd.action == RELEASE) {
                    // Desliga o MUX da porta de saída correspondente
                    mux_enable[cmd.output_port].write(false);
                    buffer_target[cmd.input_port].write(-1);
                    
                    std::cout << "@" << sc_time_stamp() << " [LocalAgent] "
                              << "Executando RELEASE na Saída " << cmd.output_port << std::endl;
                }
            }else{
                std::cout << "@" << sc_time_stamp() << " [Erro LocalAgent] Comando SDN com portas invalidas! "
                          << "In: " << cmd.input_port << ", Out: " << cmd.output_port << std::endl;
            }
        }
    }

    SC_CTOR(LocalAgent) {
        SC_THREAD(agent_thread);
    }
};