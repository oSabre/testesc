#include "TrafficInjector.h"

TrafficInjector::TrafficInjector(sc_module_name name, int num_nodes, const NetworkConfig& config) 
    :   sc_module(name),
        
        data_out("data_out", num_nodes),
        valid_out("valid_out", num_nodes),
        ready_in("ready_in", num_nodes),
        data_in("data_in", num_nodes),
        valid_in("valid_in", num_nodes),
        ready_out("ready_out", num_nodes),
        
        //path_ready_fifo("path_ready_fifo", 100),
        cfg(config){
    
    SC_THREAD(run);
    SC_THREAD(monitor_controller_responses);
    
}

void TrafficInjector::load_traffic_from_csv(const std::string& filename){
    std::ifstream file(filename);
    std::string line;
    
    // Pula o cabeçalho se houver (ex: # src, dst...)
    std::getline(file, line); 

    while (std::getline(file, line)) {
        std::stringstream ss(line);
        std::string val;
        TrafficEvent event;

        // src, dst, start_time_ns, flow_id
        std::getline(ss, val, ','); event.src = std::stoi(val);
        std::getline(ss, val, ','); event.dst = std::stoi(val);
        std::getline(ss, val, ','); event.start_time_ns = std::stod(val);
        std::getline(ss, val, ','); event.flow_id = std::stoi(val);

        //std::cout << event.src << " " << event.dst << " " << event.start_time_ns << " " << event.flow_id << std::endl;
        traffic_queue.push_back(event);
    }
    std::sort(traffic_queue.begin(), traffic_queue.end(), [](const TrafficEvent& a, const TrafficEvent& b){
        return a.start_time_ns < b.start_time_ns;
    });

    //std::cout << "Terminou"<< std::endl;
}

void TrafficInjector::run() {
    std::cout << "[RUN] Entrou TrafficInjector RUN" << std::endl;
    for (const auto& event : traffic_queue) {
        // Cria uma thread para este fluxo específico
        sc_spawn([this, event]() { this->process_traffic_flow(event); });
        std::cout << "[RUN] SPAWNED" << std::endl;
    }
}

void TrafficInjector::process_traffic_flow(TrafficEvent event) {
    std::cout << "[PROCESS_TRAFFIC_FLOW] ENTROU" << std::endl;
    // 1. Aguarda o tempo de início
    
    sc_time start_time(event.start_time_ns, SC_NS);
    sc_time current = sc_time_stamp();
    if (start_time > current) {
        wait(start_time - current);
    }
        

    // 2. Faz o pedido (Handshake de controle)
    request_path(event);

    // 3. Aguarda o sinal de pronto (Sincronização)
    wait_for_path_ready(event.flow_id);

    // 4. Envia o payload (Handshake de dados)
    send_data_payload(event);

    // 5. Libera o recurso
    release_path(event.flow_id);
}

void TrafficInjector::request_path(TrafficEvent event){
    std::cout << "[REQUEST PATH] ENTROU" << std::endl;
    PacketMetadata req;
    req.flow_id = event.flow_id;
    req.sender_id = event.src;
    req.receiver_id = event.dst;
    
    request_to_sdn.write(req);
}

void TrafficInjector::wait_for_path_ready(int flow_id){
    while(true){
        map_mutex.lock();
        if(ready_flows.count(flow_id) && ready_flows[flow_id]){
            ready_flows.erase(flow_id);
            map_mutex.unlock();
            break;
        }
        map_mutex.unlock();
        wait(ready_event);
    }
}

void TrafficInjector::monitor_controller_responses(){
    while (true) {
        // 1. Bloqueia aguardando um sinal vindo do SDN via FIFO
        int ready_id = path_ready_in.read(); 

        // 2. Atualiza o mapa de forma segura
        map_mutex.lock();
        ready_flows[ready_id] = true;
        map_mutex.unlock();

        // 3. LOG DE DEBUG (Para você confirmar a chegada)
        std::cout << "@" << sc_time_stamp() << " [TrafficInjector] "
                  << "Sinal recebido: Circuito fechado para o Flow ID " << ready_id << std::endl;

        // 4. Notifica todas as threads que estão presas no wait_for_path_ready
        ready_event.notify();
    }
}

void TrafficInjector::send_data_payload(TrafficEvent event){

}

void TrafficInjector::release_path(int flow_id){

}

