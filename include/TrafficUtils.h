#include <fstream>
#include <random>
#include <iostream>
#include <vector>
#include <cmath>
#include <utility>

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

// --- Padrões de tráfego de permutação (bit-reversal, butterfly/shuffle) ---
//
// Ambos exigem num_nodes = potência de 2 (log2 inteiro), já que operam
// sobre a representação binária do endereço do nó. Cada um define uma
// PERMUTAÇÃO fixa (cada nó tem exatamente um parceiro de destino). Se
// num_packets for maior que o número de pares únicos da permutação
// (alguns nós viram "pontos fixos" -- src==dst -- e são descartados), a
// permutação é repetida em rodadas até completar o volume pedido, para
// manter o mesmo total de tráfego que o modo "uniform" e permitir
// comparação justa entre padrões.

// Calcula k = log2(num_nodes), retornando -1 se num_nodes não for
// potência de 2 (erro de configuração para estes padrões).
static int bits_for_num_nodes(int num_nodes) {
    int k = static_cast<int>(std::round(std::log2(num_nodes)));
    if (k < 1 || (1 << k) != num_nodes) {
        return -1;
    }
    return k;
}

// Inverte a ordem dos k bits menos significativos de x.
// Ex (k=4): 5 = 0101 -> bits invertidos -> 1010 = 10.
static int bit_reverse(int x, int k) {
    int result = 0;
    for (int i = 0; i < k; ++i) {
        if (x & (1 << i)) {
            result |= (1 << (k - 1 - i));
        }
    }
    return result;
}

// Perfect shuffle: rotaciona os k bits do endereço 1 posição para a
// esquerda (o bit mais significativo "dá a volta" para o menos
// significativo). Ex (k=4): 0101 (5) -> 1010 (10).
static int left_rotate_bits(int x, int k) {
    int mask = (1 << k) - 1;
    return ((x << 1) | (x >> (k - 1))) & mask;
}

// Monta os pares (src,dst) de uma rodada da permutação dada por
// dst_fn(src, k), descartando pontos fixos (src == dst).
static std::vector<std::pair<int,int>> build_permutation_round(
        int num_nodes, int k, int (*dst_fn)(int, int)) {
    std::vector<std::pair<int,int>> round;
    for (int src = 0; src < num_nodes; ++src) {
        int dst = dst_fn(src, k);
        if (dst != src) {
            round.emplace_back(src, dst);
        }
    }
    return round;
}

// Escreve num_packets linhas no CSV, repetindo `round` ciclicamente até
// completar o total (mesmo formato/espaçamento do generateUniformTraffic:
// 100ns entre pacotes, flow_id sequencial).
static void write_permutation_csv(
        const std::vector<std::pair<int,int>>& round,
        int num_packets, const std::string& filename,
        const std::string& pattern_name) {
    if (round.empty()) {
        std::cerr << "Erro: " << pattern_name
                  << " nao gerou nenhum par valido (todos os nos sao "
                  << "pontos fixos, ou num_nodes nao e potencia de 2)."
                  << std::endl;
        return;
    }

    std::ofstream file(filename);
    if (!file.is_open()) {
        std::cerr << "Erro: Nao foi possivel criar o arquivo " << filename << std::endl;
        return;
    }
    file << "# src, dst, start_time_ns, flow_id" << "\n";

    for (int i = 0; i < num_packets; ++i) {
        const auto& p = round[i % round.size()];
        int start_time = i * 100;
        file << p.first << "," << p.second << "," << start_time << "," << i << "\n";
    }
    file.close();

    std::cout << "Arquivo " << filename << " gerado com sucesso (" << pattern_name
              << ", " << num_packets << " pacotes, " << round.size()
              << " pares unicos por rodada)." << std::endl;
}

void generateBitReversalTraffic(int num_nodes, int num_packets, const std::string& filename) {
    int k = bits_for_num_nodes(num_nodes);
    if (k < 0) {
        std::cerr << "Erro: bit-reversal exige num_nodes potencia de 2 (recebido "
                  << num_nodes << ")." << std::endl;
        return;
    }
    auto round = build_permutation_round(num_nodes, k, bit_reverse);
    write_permutation_csv(round, num_packets, filename, "bit-reversal");
}

void generateButterflyTraffic(int num_nodes, int num_packets, const std::string& filename) {
    int k = bits_for_num_nodes(num_nodes);
    if (k < 0) {
        std::cerr << "Erro: butterfly (perfect shuffle) exige num_nodes potencia de 2 (recebido "
                  << num_nodes << ")." << std::endl;
        return;
    }
    auto round = build_permutation_round(num_nodes, k, left_rotate_bits);
    write_permutation_csv(round, num_packets, filename, "butterfly (shuffle)");
}