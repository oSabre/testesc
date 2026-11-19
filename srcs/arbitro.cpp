#include "arbitro.h"

Arbitro::Arbitro(sc_module_name name, int num_cus):
    sc_module(name),
    num_cus(num_cus),
    next_cu(0){

        cu_request_ports.init(num_cus);
        SC_THREAD(arbitrate_process);
        //sensitive << clk.pos();
    }

void Arbitro::arbitrate_test_process(){
    while (true){
        //PacketMetadata req = requisitions_in.read();

        //std::cout << "[Arbitro] @ " << sc_time_stamp() 
        //          << ": Requisicao " << req.flow_id 
        //          << " chegou do roteador (injetor) " << req.sender_id 
        //          << std::endl; 
    } 
}

void Arbitro::set_config(const NetworkConfig* _cfg) {
    cfg = _cfg;
}

void Arbitro::arbitrate_process() {
    while (true) {
        // 1. Recebe a requisição (Bloqueante)
        PacketMetadata req = requisitions_in.read();

        // 2. Simula o tempo de decisão de arbitragem (latência do árbitro),
        // em ciclos. Antes era wait(1,SC_NS) hardcoded, com um comentário
        // no código original ("Ou defina um valor via cfg") indicando que
        // ficou pendente de calibração -- agora está configurável de
        // verdade via arbitro_latency_cycles. Fallback de 1 ciclo se cfg
        // nunca foi setado (não deveria acontecer em uso normal).
        int cycles = cfg ? cfg->arbitro_latency_cycles : 1;
        wait(CLOCK_PERIOD * cycles);

        // 3. Round-Robin: envia para next_cu e incrementa
        cu_request_ports[next_cu].write(req);
        
        //std::cout << "[Arbitro] @ " << sc_time_stamp() 
        //          << " -> Enviando Flow " << req.flow_id 
        //          << " para ControlUnit " << next_cu << std::endl;

        next_cu = (next_cu + 1) % num_cus; // Incremento circular
    }
}