#include <systemc.h>
#include "definitions.h"

SC_MODULE(LocalAgent) {
    sc_fifo_in<SwitchConfigCmd> config_in;

    // Confirma ao SDN_Controller que este comando foi EFETIVAMENTE
    // aplicado (nao so recebido). Sem isso, o SDN so sabia que tinha
    // ESCRITO o comando na FIFO, e usava um "wait" de margem fixa
    // (control_plane_latency) para adivinhar quando a aplicacao teria
    // terminado -- o que falhava sempre que este LocalAgent estava
    // ocupado processando um comando ANTERIOR (de outro fluxo) quando o
    // novo comando chegou, atrasando a aplicacao real alem da margem
    // assumida. O ACK elimina essa corrida por completo: o SDN so avanca
    // quando TODOS os roteadores da rota realmente confirmaram.
    sc_fifo_out<int> config_ack;

    // Pinos de saída para os MUXes
    sc_out<int> mux_sel[NUM_PORTS];
    sc_out<bool> mux_enable[NUM_PORTS];
    sc_out<int> buffer_target[NUM_PORTS];

    // Latência de propagação do plano de controle: tempo entre o comando
    // chegar (config_in.read() desbloqueia) e o LocalAgent efetivamente
    // aplicar a mudança no hardware do roteador.
    sc_time control_latency;

    void agent_thread() {
        while(true) {
            SwitchConfigCmd cmd = config_in.read();

            // Simula o atraso de propagação/decodificação do comando antes
            // de ele ter efeito real nos MUXes/Buffers. Antes, essa
            // transição era instantânea (custo zero), como se o SDN
            // Controller estivesse fisicamente colado em cada roteador.
            if (control_latency != SC_ZERO_TIME) {
                wait(control_latency);
            }

            // Validação de segurança
            if (cmd.output_port >= 0 && cmd.output_port < NUM_PORTS &&
                cmd.input_port >= 0 && cmd.input_port < NUM_PORTS) {
                if (cmd.action == SETUP) {
                    //std::cout << "[DEBUG LocalAgent] Escrevendo no buffer_target[" << cmd.input_port 
                    //        << "] o valor: " << cmd.output_port << std::endl;
                    // Configura o MUX da porta de saída correspondente
                    mux_sel[cmd.output_port].write(cmd.input_port);
                    mux_enable[cmd.output_port].write(true);
                    buffer_target[cmd.input_port].write(cmd.output_port);
                    
                    //std::cout << "@" << sc_time_stamp() << " [LocalAgent] "
                    //          << "Executando SETUP: Saida " << cmd.output_port 
                    //          << " conectada a Entrada " << cmd.input_port << std::endl;
                }else if (cmd.action == RELEASE) {
                    // Desliga o MUX da porta de saída correspondente
                    mux_enable[cmd.output_port].write(false);
                    buffer_target[cmd.input_port].write(-1);
                    
                    //std::cout << "@" << sc_time_stamp() << " [LocalAgent] "
                    //          << "Executando RELEASE na Saida " << cmd.output_port << std::endl;
                }
            }else{
                std::cout << "@" << sc_time_stamp() << " [Erro LocalAgent] Comando SDN com portas invalidas! "
                          << "In: " << cmd.input_port << ", Out: " << cmd.output_port << std::endl;
            }

            // Confirma a aplicação deste comando específico (identificado
            // por flow_id), independente do resultado acima -- inclusive no
            // ramo de erro, para nunca deixar quem está esperando o ACK
            // preso para sempre por causa de um comando malformado.
            config_ack.write(cmd.flow_id);
        }
    }

    LocalAgent(sc_module_name name, sc_time latency = SC_ZERO_TIME)
        : sc_module(name), control_latency(latency) {
        SC_THREAD(agent_thread);
    }
};