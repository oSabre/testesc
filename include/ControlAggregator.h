#include <systemc.h>
#include "definitions.h"

SC_MODULE(ControlAggregator) {
    // Portas de entrada (uma para cada CU)
    sc_vector<sc_fifo_in<int>> inputs;
    // Saída única para o Injetor
    sc_fifo_out<int> output;
    
    ControlAggregator(sc_module_name name, int num_cus) : sc_module(name), inputs("inputs", num_cus) {
        SC_THREAD(run);
    }

    void run() {
        while (true) {
            bool found = false;
            for (size_t i = 0; i < inputs.size(); ++i) {
                // Se alguma CU enviou o "ok" (flow_id)
                if (inputs[i].num_available() > 0) {
                    int flow_id = inputs[i].read();
                    //std::cout << "[Aggregator] LI o Flow " << flow_id << " da porta " << i << std::endl;
                    output.write(flow_id); // Repassa para o TrafficInjector
                    found = true;
                }
            }
            // Antes: wait(1, SC_NS) hardcoded, sem relação com o clock.
            // Agora: o agregador varre as saídas das CUs uma vez por ciclo
            // -- uma descrição fisicamente sensata de um
            // multiplexador/varredor de hardware.
            if (!found) wait(CLOCK_PERIOD); // Espera 1 ciclo se nada estiver pronto
            else wait(SC_ZERO_TIME);    // Se processou, verifica novamente no próximo delta-cycle
        }
    }
};