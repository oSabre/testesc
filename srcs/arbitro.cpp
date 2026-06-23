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

void Arbitro::arbitrate_process() {
    while (true) {
        // 1. Recebe a requisição (Bloqueante)
        PacketMetadata req = requisitions_in.read();

        // 2. Simula o tempo de decisão de arbitragem (latência do árbitro)
        wait(1, SC_NS); // Ou defina um valor via cfg

        // 3. Round-Robin: envia para next_cu e incrementa
        cu_request_ports[next_cu].write(req);
        
        //std::cout << "[Arbitro] @ " << sc_time_stamp() 
        //          << " -> Enviando Flow " << req.flow_id 
        //          << " para ControlUnit " << next_cu << std::endl;

        next_cu = (next_cu + 1) % num_cus; // Incremento circular
    }
}