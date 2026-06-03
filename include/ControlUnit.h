#ifndef CONTROL_UNIT_H
#define CONTROL_UNIT_H

#include "TopologyManager.h"
#include "definitions.h"
#include <vector>
#include <systemc.h>
#include <stats.h>
#include "routingStrategy.h"

SC_MODULE(ControlUnit) {
    sc_in_clk clk;
    sc_in<bool> rst;
    RoutingStrategy* calcRota;
    sc_fifo_in<PacketMetadata> request_in;
    sc_fifo_out<PathWrapper> path_out;
    sc_out<bool> path_ready;
    sc_out<bool> busy;

    TopologyManager* topo_manager;
    NetworkConfig cfg;

    ControlUnit(sc_module_name name, TopologyManager* tm, RoutingStrategy* strat, NetworkConfig config) 
        : sc_module(name), calcRota(strat), topo_manager(tm), cfg(config){
        busy.initialize(false);
        path_ready.initialize(false);
        SC_THREAD(routing_process);
        sensitive << clk.pos();
        //sensitive << request_valid.pos();
    }

    void routing_process(){
        std::cout << "DEBUG: " << name() << " inicializado e esperando eventos." << std::endl;
    
        while(true){
            wait(); 

            if (request_in.num_available() == 0) {
                wait(request_in.data_written_event());
            }
            
            std::cout << "@" << sc_time_stamp() << " [" << name() << "] Acordou..." << std::endl;

            PacketMetadata meta = request_in.read();

            if (!meta.requisicao_registrada) {
                meta.tempo_requisicao = sc_time_stamp();
                meta.requisicao_registrada = true;
            }

            busy.write(true);

            // LOG 1: Saber que o módulo recebeu uma requisição
            ///*
            std::cout << "@" << sc_time_stamp() << " [CU: " << name() 
                    << "] Recebeu requisicao: " << meta << std::endl;
            //*/

            int retries = 0;
            bool allocated = false;

            while(!allocated && retries < cfg.max_retries){
                
                std::cout << "[DEBUG CU] Tentando calcular rota para: " << meta.sender_id 
                        << " -> " << meta.receiver_id << std::endl;
                
                // Verificação preventiva
                if (meta.sender_id < 0 || meta.receiver_id < 0 || 
                    meta.sender_id >= topo_manager->get_num_nodes() || 
                    meta.receiver_id >= topo_manager->get_num_nodes()) {
                    
                    std::cerr << "!!! ERRO FATAL: IDs fora do intervalo! "
                            << "Src: " << meta.sender_id << ", Dst: " << meta.receiver_id 
                            << ", Max Nodes: " << topo_manager->get_num_nodes() << std::endl;
                    
                    // Finaliza o processamento desta requisição para evitar o crash
                    busy.write(false);
                    continue; 
                }

                std::vector<int> path = calcRota->calculate_route(meta.sender_id, meta.receiver_id, *topo_manager);

                if (path.empty()) {
                    wait(cfg.retry_wait_ns, SC_NS);
                    retries++;
                    continue; // Pula para a próxima requisição, sem tentar alocar nada
                }

                if(topo_manager->try_allocate_path(path)){
                    ///*
                    std::cout << "@" << sc_time_stamp() << " [CU: " << name() 
                            << "] Rota alocada com sucesso! Caminho: " << path << std::endl;
                    //*/
                    std::cout << "@" << sc_time_stamp() << " [CU: " << name() 
                          << "] Tentando escrever path_out..." << std::endl;
                    path_out.write(path);
                    std::cout << "@" << sc_time_stamp() << " [CU: " << name() 
                          << "] Sucesso na escrita path_out." << std::endl;
                    path_ready.write(true);

                    wait(cfg.link_transit_latency);

                    path_ready.write(false);
                    topo_manager->release_path(path);

                    sc_time latencia_total = sc_time_stamp() - meta.tempo_requisicao;
                    
                    std::cout << "@" << sc_time_stamp() << " [METRICA_SUCESSO] Flow " << meta.flow_id 
                                << " | Latencia: " << latencia_total 
                                << " | Src: " << meta.sender_id << " -> Dst: " << meta.receiver_id << std::endl;

                    Stats::add_entrega(latencia_total);
                    ///*
                    std::cout << "@" << sc_time_stamp() << " [CU: " << name() 
                            << "] Rota liberada: " << path << std::endl;
                    //*/
                    allocated = true;
                }else{
                    retries++;
                    wait(cfg.retry_wait_ns, SC_NS); // Representa o tempo de espera para re-arbitragem.
                }
            }

            if(!allocated){
                std::cout << "@" << sc_time_stamp() << " [WARNING] Pacote " << meta.flow_id 
                      << " descartado apos " << cfg.max_retries << " tentativas." << std::endl;
                // Idealmente aqui teria algo para tratar do descarte (como pedir para reenvio de mensagem)
            }

            busy.write(false);
        }
    }
};

#endif