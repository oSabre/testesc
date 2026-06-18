#ifndef TOPOLOGY_MANAGER_H
#define TOPOLOGY_MANAGER_H

#include <vector>
#include <iostream>
#include <map>
#include <systemc.h>

// Definimos o Link fora da classe para manter organizado
struct Link {
    int id;
    int u, v;
    bool is_busy;

    Link(int _id, int _u, int _v) : id(_id), u(_u), v(_v), is_busy(false) {}
};

class TopologyManager {
private:
    int num_nodes;
    std::vector<std::vector<int>> adj;
    std::vector<Link> links;

    std::map<std::pair<int,int>,int> link_map;
    std::map<std::pair<int, int>, int> port_map;
    std::map<int, int> port_counter;
    
    // Mutex do SystemC
    sc_mutex topo_mutex;

public:
    TopologyManager() : num_nodes(0){}

    void add_link(int id, int u, int v) {
        //topo_mutex.lock();

        int max_node = std::max(u,v);
        if(max_node >= num_nodes){
            num_nodes = max_node + 1;
            adj.resize(num_nodes);
        }

        adj[u].push_back(v);
        adj[v].push_back(u);

        links.emplace_back(id, u, v);
        int link_idx = links.size()-1;
        link_map[{std::min(u,v), std::max(u,v)}] = link_idx;

        if (port_counter.find(u) == port_counter.end()) port_counter[u] = 1;
        if (port_counter.find(v) == port_counter.end()) port_counter[v] = 1;

        int p_u = port_counter[u]++;
        int p_v = port_counter[v]++;

        port_map[{u, v}] = p_u;
        port_map[{v, u}] = p_v;

       // DEBUG para validar a atribuição
        std::cout << "Link " << id << " entre " << u << " e " << v 
              << " | " << u << " porta " << p_u 
              << " <-> " << v << " porta " << p_v << std::endl;

        //topo_mutex.unlock();
    }

    // Método essencial para o SDN Controller saber qual porta usar
    int get_port_to_neighbor(int u, int v) {
        if (port_map.count({u, v})) {
            return port_map[{u, v}];
        }
        return -1; // Erro ou nó não conectado
    }

    int get_neighbor_at_port(int u, int p) {
        for (auto const& [par, porta] : port_map) {
            if (par.first == u && porta == p) {
                return par.second; // Achou o vizinho na porta p
            }
        }
        return -1;
    }

    // Retorna referência constante para não haver cópia desnecessária
    const std::vector<std::vector<int>>& get_adj() const {
        return adj;
    }

    bool try_allocate_path(const std::vector<int>& path) {
        topo_mutex.lock();
        
        // Verifica se o caminho é válido (pelo menos 2 nós para 1 link)
        if (path.size() < 2) {
            topo_mutex.unlock();
            return false;
        }

        // 1. Verifica disponibilidade de TODOS os segmentos primeiro
        for (size_t i = 0; i < path.size() - 1; ++i) {
            int u = path[i], v = path[i+1];
            auto it = link_map.find({std::min(u, v), std::max(u, v)});
            
            if (it == link_map.end() || links[it->second].is_busy) {
                topo_mutex.unlock();
                return false; 
            }
        }

        // 2. Aloca (marca como busy)
        for (size_t i = 0; i < path.size() - 1; ++i) {
            int u = path[i], v = path[i+1];
            int idx = link_map[{std::min(u, v), std::max(u, v)}];
            links[idx].is_busy = true;
        }

        topo_mutex.unlock();
        return true;
    }

    void release_path(const std::vector<int>& path) {
        topo_mutex.lock();
        
        for (size_t i = 0; i < path.size() - 1; ++i) {
            int u = path[i], v = path[i+1];
            auto it = link_map.find({std::min(u, v), std::max(u, v)});
            if (it != link_map.end()) {
                links[it->second].is_busy = false;
            }
        }
        
        topo_mutex.unlock();
    }

    int get_num_nodes() const { return num_nodes; }

    const std::vector<Link>& get_links() const {
        return links;
    }

    bool is_link_busy(int u, int v){
        auto it = link_map.find({std::min(u, v), std::max(u, v)});
        if(it != link_map.end()){
            return links[it->second].is_busy;
        }
        return true;
    }

};

#endif