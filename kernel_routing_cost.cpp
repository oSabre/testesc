// [copia com coluna qcal: custo por operacao no formato do simulador, para custo_por_topologia.py]
// kernel_routing.cpp  --  Fase 0.7
// BFS e Dijkstra do ControlUnit::calculate_dijkstra, isolados do SystemC e
// reescritos com estruturas de dados planas (vetores, sem std::map/vector
// dentro da regiao medida), para serem medidos no gem5 (RISC-V, modo SE).
//
// Uso:  kernel_routing topo.txt saida.csv K semente busy_pct
//   topo.txt : 1a linha "N L"; depois L linhas "u v" (enlaces nao dirigidos)
//   K        : numero de pares (src,dst) sorteados
//   busy_pct : % de enlaces marcados ocupados (sorteados de novo a cada par)
//
// Para cada par, e para cada algoritmo (bfs, depois dijkstra):
//   1) uma chamada de aquecimento (fora da medicao: caches/preditor quentes);
//   2) m5_reset_stats(); kernel; m5_dump_stats();   <- bloco de estatisticas
// Ordem dos blocos em stats.txt: par0-bfs, par0-dij, par1-bfs, par1-dij, ...
// (o ultimo bloco, do fim da simulacao, e descartado pelo calibrate.py).
// Os contadores (nos visitados, arestas examinadas, operacoes de fila, soma
// de log2 do tamanho da fila) sao calculados por uma repeticao FORA da regiao
// medida (template CNT=true), entao nao poluem a contagem de instrucoes.
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cmath>
#include <climits>
#ifdef USE_M5
#include <gem5/m5ops.h>
#define M5_RESET() m5_reset_stats(0, 0)
#define M5_DUMP()  m5_dump_stats(0, 0)
#else
#define M5_RESET() ((void)0)
#define M5_DUMP()  ((void)0)
#endif

#ifndef PQ_OP
#define PQ_OP 11
#endif
static constexpr int MAXN = 1024;   // chaves do heap usam 10 bits para o no
static constexpr int NP = 5;        // 4 portas de rede + local (vizinho = -1)
static constexpr int HEAPMAX = 8192;

static int N_ = 0, L_ = 0;
static int nbr[MAXN][NP];           // vizinho na porta p, ou -1
static unsigned char busy[MAXN][NP];// enlace (u -> nbr[u][p]) ocupado
static int path_out[MAXN];
static volatile int path_len_out;   // evita que o compilador elimine o kernel

struct Cnt {
    long long visited = 0, pops = 0, pushes = 0, ops = 0, edges = 0;
    double log2sum = 0.0;
    long long sift = 0;             // passos reais de subida/descida no heap
    long long qcal = 0;             // soma de max(1, llround(PQ_OP*log2(arg))) por operacao de heap (Dijkstra)
    long long model_cycles = 0;     // modelo atual (todos os coeficientes = 1)
};

// ------------------------------------------------------------------ BFS
template <bool CNT>
static int run_bfs(int src, int dst, Cnt* c) {
    static unsigned char seen[MAXN];
    static int prev[MAXN];
    static int fifo[MAXN];
    int head = 0, tail = 0;
    for (int i = 0; i < N_; ++i) { seen[i] = 0; prev[i] = -1; }   // init O(N)
    seen[src] = 1;
    fifo[tail++] = src;
    while (head < tail) {
        int u = fifo[head++];
        for (int p = 0; p < NP; ++p) {
            int v = nbr[u][p];
            if (v < 0) continue;
            if (CNT) c->edges++;
            if (!busy[u][p] && !seen[v]) {
                seen[v] = 1; prev[v] = u; fifo[tail++] = v;
            }
        }
    }
    int len = 0;
    if (seen[dst]) {
        for (int at = dst; at != -1; at = prev[at]) path_out[len++] = at;
        for (int i = 0, j = len - 1; i < j; ++i, --j) {
            int t = path_out[i]; path_out[i] = path_out[j]; path_out[j] = t;
        }
    }
    if (CNT) {
        c->visited = tail; c->pops = tail; c->pushes = tail - 1;
        c->ops = 1 + c->pops + c->pushes;
        // dispatch(1) + init*N + q_op*(1+pops+pushes) + e_op*edges
        c->model_cycles = 1 + N_ + c->ops + c->edges;
    }
    return len;
}

// ------------------------------------------------------------- Dijkstra
static unsigned heap_[HEAPMAX];
static int hsize_;
template <bool CNT>
static inline void hpush(unsigned key, long long* s) {
    int i = hsize_++;
    while (i > 0) {
        int p = (i - 1) >> 1;
        if (heap_[p] <= key) break;
        if (CNT) ++*s;
        heap_[i] = heap_[p]; i = p;
    }
    heap_[i] = key;
}
template <bool CNT>
static inline unsigned hpop(long long* s) {
    unsigned top = heap_[0];
    unsigned key = heap_[--hsize_];
    if (hsize_ > 0) {
        int i = 0;
        for (;;) {
            int ch = 2 * i + 1;
            if (ch >= hsize_) break;
            if (ch + 1 < hsize_ && heap_[ch + 1] < heap_[ch]) ch++;
            if (heap_[ch] >= key) break;
            if (CNT) ++*s;
            heap_[i] = heap_[ch]; i = ch;
        }
        heap_[i] = key;
    }
    return top;
}

template <bool CNT>
static int run_dij(int src, int dst, Cnt* c) {
    static int dist[MAXN];
    static int prev[MAXN];
    hsize_ = 0;
    for (int i = 0; i < N_; ++i) { dist[i] = INT_MAX; prev[i] = -1; }   // init O(N)
    long long mc = 1 + N_;           // modelo: dispatch + init*N
    auto opc = [&](double arg) {     // pq_op_cost do original (coef = 1)
        long long r = std::llround(std::log2(arg));
        return r < 1 ? 1LL : r;
    };
    dist[src] = 0;
    hpush<CNT>((0u << 10) | (unsigned)src, CNT ? &c->sift : nullptr);
    if (CNT) { c->ops++; c->log2sum += std::log2(hsize_ + 1.0); mc += opc(hsize_ + 1.0); c->qcal += std::max(1LL, (long long)std::llround(PQ_OP * std::log2(hsize_ + 1.0))); }
    while (hsize_ > 0) {
        unsigned key = hpop<CNT>(CNT ? &c->sift : nullptr);
        int d = (int)(key >> 10), u = (int)(key & 1023u);
        if (CNT) { c->pops++; c->ops++; c->log2sum += std::log2(hsize_ + 2.0); mc += opc(hsize_ + 2.0); c->qcal += std::max(1LL, (long long)std::llround(PQ_OP * std::log2(hsize_ + 2.0))); }
        if (d > dist[u]) continue;   // entrada obsoleta
        for (int p = 0; p < NP; ++p) {
            int v = nbr[u][p];
            if (v < 0) continue;
            if (CNT) { c->edges++; mc += 1; }
            if (!busy[u][p]) {
                if (dist[u] + 1 < dist[v]) {
                    dist[v] = dist[u] + 1; prev[v] = u;
                    if (CNT) { c->pushes++; c->ops++; c->log2sum += std::log2(hsize_ + 1.0); mc += opc(hsize_ + 1.0); c->qcal += std::max(1LL, (long long)std::llround(PQ_OP * std::log2(hsize_ + 1.0))); }
                    hpush<CNT>(((unsigned)dist[v] << 10) | (unsigned)v, CNT ? &c->sift : nullptr);
                }
            }
        }
    }
    int len = 0;
    if (dist[dst] != INT_MAX) {
        for (int at = dst; at != -1; at = prev[at]) path_out[len++] = at;
        for (int i = 0, j = len - 1; i < j; ++i, --j) {
            int t = path_out[i]; path_out[i] = path_out[j]; path_out[j] = t;
        }
    }
    if (CNT) {
        long long vis = 0;
        for (int i = 0; i < N_; ++i) vis += (dist[i] != INT_MAX);
        c->visited = vis; c->model_cycles = mc;
    }
    return len;
}

// --------------------------------------------------------------- driver
static uint64_t rng_state = 1;
static inline uint32_t rnd() {
    rng_state = rng_state * 6364136223846793005ULL + 1442695040888963407ULL;
    return (uint32_t)(rng_state >> 33);
}

static void set_busy(int pct, int* eu, int* ev, int L) {
    for (int i = 0; i < N_; ++i) for (int p = 0; p < NP; ++p) busy[i][p] = 0;
    if (pct <= 0) return;
    for (int e = 0; e < L; ++e) {
        if ((int)(rnd() % 100) < pct) {
            int u = eu[e], v = ev[e];
            for (int p = 0; p < NP; ++p) if (nbr[u][p] == v) busy[u][p] = 1;
            for (int p = 0; p < NP; ++p) if (nbr[v][p] == u) busy[v][p] = 1;
        }
    }
}

int main(int argc, char** argv) {
    if (argc < 6) {
        std::fprintf(stderr, "uso: %s topo.txt saida.csv K semente busy_pct\n", argv[0]);
        return 1;
    }
    FILE* ft = std::fopen(argv[1], "r");
    if (!ft) { std::perror("topo"); return 1; }
    int N, L;
    if (std::fscanf(ft, "%d %d", &N, &L) != 2 || N > MAXN || N < 2) { std::fprintf(stderr, "topo invalida\n"); return 1; }
    static int eu[4 * MAXN], ev[4 * MAXN];
    if (L > 4 * MAXN) { std::fprintf(stderr, "L grande demais\n"); return 1; }
    N_ = N; L_ = L;
    for (int i = 0; i < N; ++i) for (int p = 0; p < NP; ++p) nbr[i][p] = -1;
    for (int e = 0; e < L; ++e) {
        int u, v;
        if (std::fscanf(ft, "%d %d", &u, &v) != 2) { std::fprintf(stderr, "topo truncada\n"); return 1; }
        eu[e] = u; ev[e] = v;
        int pu = 0; while (pu < 4 && nbr[u][pu] != -1) ++pu;
        int pv = 0; while (pv < 4 && nbr[v][pv] != -1) ++pv;
        if (pu >= 4 || pv >= 4) { std::fprintf(stderr, "grau > 4 no no %d ou %d\n", u, v); return 1; }
        nbr[u][pu] = v; nbr[v][pv] = u;
    }
    std::fclose(ft);
    int K = std::atoi(argv[3]);
    rng_state = (uint64_t)std::atoll(argv[4]) * 2654435761ULL + 12345ULL;
    int busy_pct = std::atoi(argv[5]);

    FILE* fo = std::fopen(argv[2], "w");
    if (!fo) { std::perror("saida"); return 1; }
    std::fprintf(fo, "call,algo,src,dst,N,L,busy_pct,visited,pops,pushes,ops,edges,log2sum,model_cycles,reached,path_len,sift,qcal\n");

    for (int k = 0; k < K; ++k) {
        int src = (int)(rnd() % N), dst = (int)(rnd() % (N - 1));
        if (dst >= src) ++dst;
        set_busy(busy_pct, eu, ev, L);

        for (int a = 0; a < 2; ++a) {
            // aquecimento (fora da medicao)
            int len = (a == 0) ? run_bfs<false>(src, dst, nullptr)
                               : run_dij<false>(src, dst, nullptr);
            // regiao medida
            M5_RESET();
            len = (a == 0) ? run_bfs<false>(src, dst, nullptr)
                           : run_dij<false>(src, dst, nullptr);
            M5_DUMP();
            path_len_out = len;
            // contadores (repeticao instrumentada, fora da medicao)
            Cnt c;
            int len2 = (a == 0) ? run_bfs<true>(src, dst, &c) : run_dij<true>(src, dst, &c);
            if (len2 != len) { std::fprintf(stderr, "ERRO: caminhos diferentes\n"); return 2; }
            std::fprintf(fo, "%d,%s,%d,%d,%d,%d,%d,%lld,%lld,%lld,%lld,%lld,%.6f,%lld,%d,%d,%lld,%lld\n",
                         k, a == 0 ? "bfs" : "dijkstra", src, dst, N, L, busy_pct,
                         c.visited, c.pops, c.pushes, c.ops, c.edges, c.log2sum,
                         c.model_cycles, len > 0 ? 1 : 0, len, c.sift, c.qcal);
        }
    }
    std::fclose(fo);
    std::printf("ok: %d pares x 2 algoritmos\n", K);
    return 0;
}