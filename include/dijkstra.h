#include "RoutingStrategy.h"
#include <queue>
#include <algorithm>
#include <limits>
#include <systemc.h>

class dijkstra : public RoutingStrategy {
public:
    std::vector<int> calculate_route(int src, int dst, const TopologyManager& tm) override {
        const auto& adj = tm.get_adj();
        int n = adj.size();

        double custo_ns = 0.0;

        std::vector<int> dist(n, std::numeric_limits<int>::max());
        std::vector<int> parent(n, -1);
        std::priority_queue<std::pair<int, int>, std::vector<std::pair<int, int>>, std::greater<>> pq;

        dist[src] = 0;
        pq.push({0, src});
        custo_ns += (1.0 * std::log2(pq.size()+1));

        while (!pq.empty()) {
            //int n = pq.size();
            int u = pq.top().second;
            pq.pop();
            custo_ns += (1.5 * std::log2(pq.size() + 2));

            if (u == dst) break;

            for (int v : adj[u]) {
                custo_ns += 0.2;
                if (dist[u] + 1 < dist[v]) {
                    dist[v] = dist[u] + 1;
                    parent[v] = u;
                    custo_ns += (1.0*std::log2(pq.size()+1));
                    pq.push({dist[v], v});
                }
            }
        }
        

        wait(custo_ns, SC_NS);

        if (parent[dst] == -1 && src != dst) {
            return {}; // Retorna vetor vazio se não houver caminho
        }

        std::vector<int> path;
        for (int v = dst; v != -1; v = parent[v]) path.push_back(v);
        std::reverse(path.begin(), path.end());

        return path;
    }
};