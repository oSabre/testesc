#include <fstream>
#include <random>
#include <iostream>

void generateUniformTraffic(int num_nodes, int num_packets, int seed, const std::string& filename) {
    std::ofstream file(filename);
    if (!file.is_open()) {
        std::cerr << "Erro: Nao foi possivel criar o arquivo " << filename << std::endl;
        return;
    }

    file << "# src, dst, start_time_ns, flow_id" << "\n";

    std::mt19937 rng(seed);
    std::uniform_int_distribution<int> dist(0, num_nodes - 1);

    // Ajuste o formato abaixo para bater exatamente com o que seu load_traffic_from_csv espera!
    // Exemplo comum: id, src, dst, start_time
    for (int i = 0; i < num_packets; ++i) {
        int src = dist(rng);
        int dst = dist(rng);
        while (src == dst) dst = dist(rng); // Garante que src != dst

        int start_time = i * 100; // Espaçamento fixo entre pacotes (ex: 100ns)
        //int flow_id = i + 1;
        
        file << src << "," << dst << "," << start_time << "," << i << "\n";
    }

    file.close();
    std::cout << "Arquivo " << filename << " gerado com sucesso (" << num_packets << " pacotes)." << std::endl;
}