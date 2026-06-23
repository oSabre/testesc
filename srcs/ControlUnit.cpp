#include "ControlUnit.h"
#include <iostream>
#include "SDN_Controller.h"

ControlUnit::ControlUnit(sc_module_name name) : sc_module(name) {
    // Registra a thread que vai ficar escutando a FIFO
    SC_THREAD(process_routing);
}

void ControlUnit::process_routing() {
    while (true) {
        // 1. Bloqueia a thread até que o Árbitro mande uma requisição
        PacketMetadata req = request_in.read();
        bool path_allocated = false;
        std::vector<int> route;

        // 2. Log para validar que a mensagem chegou e qual CU processou
        //std::cout << "[ControlUnit " << name() << "] @ " << sc_time_stamp() 
        //          << ": Processando calculo de rota para Flow ID " << req.flow_id 
         //         << " (Origem: " << req.sender_id 
         //         << " -> Destino: " << req.receiver_id << ")" << std::endl;

        // 3. Simula um tempo de processamento (latência do cálculo da rota)
        // Por enquanto vamos colocar um tempo fixo
        wait(5, SC_NS); 

        //std::cout << "[ControlUnit " << name() << "] @ " << sc_time_stamp() 
        //  << ": Acordou do processamento, iniciando loop de alocacao." << std::endl;

        while(!path_allocated){
            // --- INSERÇÃO DOS LOGS DE DIAGNÓSTICO ---
            // 1. Validar se os IDs estão dentro do esperado
            if (req.sender_id >= tm->get_num_nodes() || req.receiver_id >= tm->get_num_nodes()) {
                std::cerr << "[ERRO CRÍTICO] " << name() << " IDs de nó fora do limite! "
                        << "Src: " << req.sender_id << ", Dst: " << req.receiver_id 
                        << " | Grafo atual tem " << tm->get_num_nodes() << " nós." << std::endl;
            }

            // 2. Log de pré-processamento
            std::cout << "[DEBUG] " << name() << " calculando rota: " 
                    << req.sender_id << " -> " << req.receiver_id << std::endl;
            // ----------------------------------------

            route = calculate_dijkstra(req.sender_id, req.receiver_id);

            if (route.empty()) {
                // Não há caminhos livres na topologia inteira.
                // Espera um tempo para que alguma mensagem termine e libere a rede.
                std::cout << "[ControlUnit " << name() << "] @ " << sc_time_stamp() 
                        << ": ERRO: Dijkstra retornou rota vazia (caminho impossivel?)." << std::endl;

                wait(cfg->retry_wait_ns, SC_NS); 
                continue; 
            }

            path_allocated = tm->try_allocate_path(route);

            if(path_allocated){
                //std::cout << "[ControlUnit] Rota encontrada e reservada para o Flow " << req.flow_id 
                //          << " (CU: " << this->name() << ")" << std::endl;
                parent_sdn->configure_path_hardware(route, req.flow_id);
                path_ready_out.write(req.flow_id);
            }else{
                //std::cout << "[ControlUnit " << name() << "] @ " << sc_time_stamp() 
                //            << ": Caminho para Flow " << req.flow_id << " BUSY. Tentando novamente em " 
                 //           << cfg->retry_wait_ns << " ns." << std::endl;
                wait(cfg->retry_wait_ns, SC_NS);
            }

        }
    }
}

void ControlUnit::set_topology(TopologyManager* _tm){
    tm = _tm;
}

std::vector<int> ControlUnit::calculate_dijkstra(int src, int dst){
    int num_nodes = tm->get_num_nodes();

    const int INF = std::numeric_limits<int>::max();
    std::vector<int> dist(num_nodes, INF);
    std::vector<int> prev(num_nodes, -1);

    std::priority_queue<
        std::pair<int,int>,
        std::vector<std::pair<int,int>>,
        std::greater<std::pair<int,int>>
    > pq;

    dist[src] = 0;
    pq.push({0, src});

    while(!pq.empty()){
        int d = pq.top().first;
        int u = pq.top().second;
        pq.pop();

        if (u==dst) break;

        if (d>dist[u]) continue;

        for(int p = 0; p < 5; ++p){
            int v = tm->get_neighbor_at_port(u,p);

            if(v!=-1 && !tm->is_link_busy(u,v)){
                int weight = 1;
                if(dist[u] + weight < dist[v]){
                    dist[v] = dist[u] + weight;
                    prev[v] = u;
                    pq.push({dist[v],v});
                }
            }
        }
    }

    std::vector<int> path;
    for (int at = dst; at != -1; at = prev[at]) {
        path.push_back(at);
    }

    std::reverse(path.begin(), path.end());

    if (path.empty() || path[0] != src) {
        //std::cout << "[ControlUnit] AVISO: Nenhum caminho encontrado de " << src << " para " << dst << std::endl;
        return std::vector<int>(); // Retorna vetor vazio
    }

    return path;
}

void ControlUnit::set_config(const NetworkConfig* _cfg) {
    cfg = _cfg;
}

void ControlUnit::set_parent(SDN_Controller* sdn){
    parent_sdn = sdn;
}