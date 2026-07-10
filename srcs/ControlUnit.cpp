#include "ControlUnit.h"
#include <iostream>
#include <cmath>
#include <random>
#include <functional>
#include "SDN_Controller.h"

ControlUnit::ControlUnit(sc_module_name name) : sc_module(name) {
    // Registra a thread que vai ficar escutando a FIFO
    SC_THREAD(process_routing);
}

void ControlUnit::process_routing() {
    // Gerador de números aleatórios local a esta thread (persiste durante
    // toda a vida da SC_THREAD, já que process_routing nunca retorna).
    // Semeado deterministicamente a partir do nome do módulo, para manter
    // a simulação reprodutível entre execuções (mesma config -> mesmo
    // resultado), em vez de usar std::random_device.
    // Semente combina o nome do módulo (para que cada CU tenha um stream
    // diferente dentro da MESMA execução) com o master_seed vindo do
    // config.json (para que EXECUÇÕES/réplicas diferentes, variando
    // simulation.seed, produzam jitter de retry diferente). Sem o
    // master_seed, duas réplicas do mesmo binário dariam exatamente o
    // mesmo resultado, pois o hash do nome sozinho é fixo entre execuções.
    std::mt19937 rng(std::hash<std::string>{}(std::string(name()))
                      ^ static_cast<std::size_t>(cfg->master_seed));

    // Espera o tempo de retry configurado + um jitter aleatório uniforme
    // em [0, retry_jitter_ns]. Sem o jitter, vários fluxos que colidem no
    // mesmo link/CU re-tentam sempre no mesmo instante simulado exato,
    // criando um "thundering herd" sincronizado que não reflete o
    // comportamento disperso de um sistema real.
    auto wait_retry = [&]() {
        std::uniform_int_distribution<int> jitter_dist(0, std::max(0, cfg->retry_jitter_ns));
        int jitter = jitter_dist(rng);
        wait(cfg->retry_wait_ns + jitter, SC_NS);
    };

    while (true) {
        // 1. Bloqueia a thread até que o Árbitro mande uma requisição
        PacketMetadata req = request_in.read();
        bool path_allocated = false;
        bool flow_discarded = false;
        int retry_count = 0;
        std::vector<int> route;

        // Conta mais uma tentativa falha e diz se já é hora de desistir
        // deste fluxo. Precisa ser declarada AQUI DENTRO (e não junto de
        // wait_retry, lá em cima) porque captura retry_count por
        // referência, e retry_count só existe a partir desta iteração do
        // laço -- uma lambda definida antes do laço não conseguiria
        // enxergar uma variável declarada depois dela.
        //
        // Sem esse contador (problema #8), esta CU ficava presa em retry
        // infinito para qualquer fluxo que nunca conseguisse alocar
        // caminho, bloqueando o round-robin do Arbitro para sempre e
        // travando a fila de todos os fluxos seguintes atribuídos a ela.
        auto exceeded_max_retries = [&]() {
            retry_count++;
            return retry_count >= cfg->max_retries;
        };

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

        // Segunda camada de defesa: origem == destino nunca gera uma rota
        // alocável (try_allocate_path sempre recusa caminhos de tamanho 1).
        // O TrafficInjector já filtra isso antes de enviar a requisição, mas
        // se essa CU receber um pedido assim por qualquer outro caminho,
        // é melhor descartar e liberar a CU do que entrar num retry infinito
        // que travaria esse núcleo (e, por consequência, o round-robin do
        // Arbitro) para sempre.
        if (req.sender_id == req.receiver_id) {
            std::cerr << "[ControlUnit " << name() << "] AVISO: Requisicao invalida "
                      << "(origem == destino == " << req.sender_id << ") para Flow "
                      << req.flow_id << ". Descartando." << std::endl;
            continue;
        }

        while(!path_allocated){
            // --- INSERÇÃO DOS LOGS DE DIAGNÓSTICO ---
            // 1. Validar se os IDs estão dentro do esperado
            if (req.sender_id >= tm->get_num_nodes() || req.receiver_id >= tm->get_num_nodes()) {
                std::cerr << "[ERRO CRÍTICO] " << name() << " IDs de nó fora do limite! "
                        << "Src: " << req.sender_id << ", Dst: " << req.receiver_id 
                        << " | Grafo atual tem " << tm->get_num_nodes() << " nós." << std::endl;
            }

            // 2. Log de pré-processamento
            //std::cout << "[DEBUG] " << name() << " calculando rota: " 
            //        << req.sender_id << " -> " << req.receiver_id << std::endl;
            // ----------------------------------------

            route = calculate_dijkstra(req.sender_id, req.receiver_id);

            if (route.empty()) {
                // Não há caminhos livres na topologia inteira.
                // Espera um tempo para que alguma mensagem termine e libere a rede.
                std::cout << "[ControlUnit " << name() << "] @ " << sc_time_stamp() 
                        << ": ERRO: Dijkstra retornou rota vazia (caminho impossivel?)." << std::endl;

                if (exceeded_max_retries()) {
                    flow_discarded = true;
                    break;
                }

                wait_retry();
                continue; 
            }

            path_allocated = tm->try_allocate_path(route);

            if(path_allocated){
                //std::cout << "[ControlUnit] Rota encontrada e reservada para o Flow " << req.flow_id 
                //          << " (CU: " << this->name() << ")" << std::endl;
                parent_sdn->configure_path_hardware(route, req.flow_id);

                // CRÍTICO: configure_path_hardware só ESCREVE os comandos SETUP
                // nas FIFOs dos roteadores -- cada LocalAgent ainda precisa
                // ler e aplicar o efeito real (buffer_target/mux_sel/mux_enable).
                // Um "wait" de margem fixa (control_plane_latency + 1ns) não
                // era suficiente: se algum LocalAgent da rota já estivesse
                // ocupado aplicando o comando de OUTRO fluxo concorrente no
                // mesmo instante, o nosso comando ficava esperando na fila
                // dele, atrasando a aplicação real além da margem assumida.
                // Isso causava exatamente o bug do "fluxo 35": o flit
                // chegava no InputBuffer antes do buffer_target ser
                // configurado, era descartado silenciosamente, o fluxo
                // nunca completava, o teardown nunca acontecia, e os links
                // da rota ficavam PERMANENTEMENTE presos como ocupados.
                //
                // A correção correta é esperar a CONFIRMAÇÃO real (ACK) de
                // que todos os roteadores da rota já aplicaram o comando,
                // em vez de adivinhar um tempo fixo.
                parent_sdn->wait_for_route_ack(req.flow_id, route);

                path_ready_out.write(req.flow_id);
            }else{
                //std::cout << "[ControlUnit " << name() << "] @ " << sc_time_stamp() 
                //            << ": Caminho para Flow " << req.flow_id << " BUSY. Tentando novamente em " 
                 //           << cfg->retry_wait_ns << " ns." << std::endl;
                if (exceeded_max_retries()) {
                    flow_discarded = true;
                    break;
                }
                wait_retry();
            }

        }

        // O fluxo esgotou max_retries sem conseguir alocar caminho: desiste
        // dele, reporta o descarte (para ele aparecer explicitamente como
        // DESCARTADO_TIMEOUT no relatório em vez de ficar preso/sumir) e
        // libera esta CU imediatamente para o próximo pedido da fila.
        if (flow_discarded) {
            std::cerr << "[ControlUnit " << name() << "] @ " << sc_time_stamp()
                      << ": Flow " << req.flow_id << " DESCARTADO apos " << retry_count
                      << " tentativas (max_retries=" << cfg->max_retries << ")." << std::endl;
            parent_sdn->report_flow_discarded(req.flow_id);
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

    // --- Modelo de custo computacional do Dijkstra ---
    // Antes: tempo fixo (wait(5, SC_NS) no process_routing), igual para
    // qualquer topologia e qualquer par origem/destino.
    // Agora: o custo escala com o trabalho real do algoritmo (O((V+E) log V)):
    //   1) Custo de inicialização O(V): alocar/zerar dist[]/prev[], que
    //      cresce com o tamanho da rede (num_nodes).
    //   2) Custo de operações de heap O(log V) por push/pop na priority_queue.
    //   3) Custo de examinar cada aresta candidata, incluindo a consulta ao
    //      estado do link (is_link_busy) — um controlador real também paga
    //      um custo para consultar o estado atual da rede.
    // Os coeficientes vêm do NetworkConfig (calibráveis via config.json).
    double custo_ns = cfg->dijkstra_base_ns_per_node * num_nodes;

    dist[src] = 0;
    pq.push({0, src});
    custo_ns += cfg->dijkstra_pq_op_ns * std::log2(pq.size() + 1.0);

    while(!pq.empty()){
        int d = pq.top().first;
        int u = pq.top().second;
        pq.pop();
        custo_ns += cfg->dijkstra_pq_op_ns * std::log2(pq.size() + 2.0);

        if (u==dst) break;

        if (d>dist[u]) continue;

        for(int p = 0; p < NUM_PORTS; ++p){
            int v = tm->get_neighbor_at_port(u,p);
            if (v == -1) continue;

            // Custo de examinar a aresta candidata (vizinho + consulta ao
            // estado atual do link).
            custo_ns += cfg->dijkstra_edge_check_ns;

            if(!tm->is_link_busy(u,v)){
                int weight = 1;
                if(dist[u] + weight < dist[v]){
                    dist[v] = dist[u] + weight;
                    prev[v] = u;
                    custo_ns += cfg->dijkstra_pq_op_ns * std::log2(pq.size()+1.0);
                    pq.push({dist[v],v});
                }
            }
        }
    }

    // Aplica o custo computacional simulado desta chamada. Importante: como
    // calculate_dijkstra é chamado de novo a cada retry (o estado dos links
    // pode ter mudado), cada tentativa paga o custo de recalcular a rota do
    // zero — o que é o comportamento real de um controlador que refaz o
    // cálculo sob nova informação de estado da rede.
    wait(custo_ns, SC_NS);

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