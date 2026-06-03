#include <systemc.h>
#include "TopologyManager.h"
#include "Arbitro.h"
#include "ControlUnit.h"
#include "definitions.h"
#include "TrafficGenerator.h"
#include <stats.h>
#include "dijkstra.h"

int sc_main(int argc, char* argv[]) {
    // 1. Definições de Escala
    const int N_ROUTERS = 5;
    const int N_CUS = 1;

    // 2. Sinais de Clock e Reset
    sc_clock clk("clk", 10, SC_NS);
    sc_signal<bool> rst;

    // 3. Gerenciador de Topologia (Instância única)
    TopologyManager* tm = new TopologyManager();

    tm->add_link(0, 0, 1);
    tm->add_link(1, 1, 2); 
    tm->add_link(2, 2, 3);
    tm->add_link(3, 3, 4);
    tm->add_link(4, 4, 0);
    //tm->add_link(4, 100, 101);

    // 4. Canais de comunicação (FIFOs entre Roteadores e Árbitro)
    sc_vector<sc_fifo<PacketMetadata>> router_to_arb_fifo("router_to_arb_fifo", N_ROUTERS);

    // 5. Instanciar o Árbitro
    Arbitro arb("Arbitro", N_ROUTERS, N_CUS);
    arb.clk(clk);

    // Instanciar Geradores de Tráfego
    //std::vector<TrafficGenerator*> generators(N_ROUTERS);
    /*
    for (int i = 0; i < N_ROUTERS; ++i) {
        generators[i] = new TrafficGenerator(sc_gen_unique_name("Gen"), false, sc_time(50, SC_NS));
        generators[i]->clk(clk);
        generators[i]->out_fifo(router_to_arb_fifo[i]);
    }
    */
    TrafficGenerator* gen = new TrafficGenerator("Gen_Unico", false, sc_time(50, SC_NS));
    gen->clk(clk);
    gen->out_fifo(router_to_arb_fifo[0]);

    // 6. Instanciar as Control Units
    std::vector<ControlUnit*> cus(N_CUS);
    
    // USANDO FIFO PARA COMUNICAÇÃO ARBITRO -> CU
    sc_vector<sc_fifo<PacketMetadata>> cu_req_fifo("cu_req_fifo", N_CUS);
    
    // Mantemos sinais para Busy e Ready (são flags de controle)
    sc_vector<sc_signal<bool>> cu_busy_sig("cu_busy_sig", N_CUS);
    sc_vector<sc_fifo<PathWrapper>> cu_path_fifo("cu_path_fifo", N_CUS);
    sc_vector<sc_signal<bool>> cu_ready_sig("cu_ready_sig", N_CUS);

    for (int i = 0; i < N_CUS; ++i) {
        cus[i] = new ControlUnit(sc_gen_unique_name("CU"), tm, new dijkstra());
        cus[i]->clk(clk);
        cus[i]->rst(rst);
        
        // Conexões Árbitro -> CU
        arb.cu_request_out[i](cu_req_fifo[i]); // Conecta ao FIFO
        arb.cu_busy[i](cu_busy_sig[i]);
        
        // Conexões CU -> Sistema
        cus[i]->request_in(cu_req_fifo[i]);    // CU lê do FIFO
        cus[i]->path_out(cu_path_fifo[i]);
        cus[i]->path_ready(cu_ready_sig[i]);
        cus[i]->busy(cu_busy_sig[i]);
    }

    // Conexão Roteadores -> Árbitro
    for (int i = 0; i < N_ROUTERS; ++i) {
        arb.router_reqs[i](router_to_arb_fifo[i]);
    }

    // 7. Simulação
    cout << "Iniciando Simulacao..." << endl;
    sc_start(300, SC_NS);
    cout << "Simulacao Finalizada." << endl;

    // Relatório Final Consolidado
    cout << "\n========================================" << endl;
    cout << "RELATORIO DE DESEMPENHO SDNoC" << endl;

    //cout << "Pacotes entregues: " << Stats::entregues << endl;
    
    if (Stats::entregues > 0) {
        double media_segundos = (Stats::latencia_total.to_seconds() / Stats::entregues);
    
        // Exibe convertido para nanosegundos com 2 casas decimais
        cout << "Latencia Media: " << (media_segundos * 1e9) << " ns" << endl;
        
        // Vazão mantida
        double tempo_total_ns = sc_time_stamp().to_seconds() * 1e9;
        cout << "Vazao (Pacotes/ns): " << (double)Stats::entregues / tempo_total_ns << endl;

        cout << "Pacotes gerados: " << Stats::gerados << endl;
        cout << "Pacotes entregues: " << Stats::entregues << endl;
        cout << "Eficiencia: " << Stats::calcular_eficiencia() << " %" << endl;
        /*
        sc_time media = Stats::latencia_total / Stats::entregues;
        double tempo_total = sc_time_stamp().to_seconds() * 1e9;
        cout << "Latencia Media: " << media << endl;
        cout << "Vazao (Pacotes/ns): " << (double)Stats::entregues / tempo_total << endl;
        */
    }
    cout << "========================================\n" << endl;

    return 0;
}