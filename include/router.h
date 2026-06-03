#ifndef ROUTER_H
#define ROUTER_H

#include <systemc.h>
#include "definitions.h"
#include "elastic_buffer.h"
#include "output_mux.h"

SC_MODULE(Router) {
    int id;
    sc_in_clk clk;
    sc_in<bool> rst;

    // Portas externas do roteador
    sc_in<Flit> in_ports[NUM_PORTS];
    sc_out<Flit> out_ports[NUM_PORTS];
    sc_in<bool> ready_in[NUM_PORTS];  // O roteador recebe "estou pronto" do vizinho
    sc_out<bool> ready_out[NUM_PORTS];
    sc_in<bool> in_valid[NUM_PORTS];
    sc_out<bool> valid_out[NUM_PORTS]; // O roteador envia "dado válido" para o vizinho
    // Interface SDN: IRT e ORT (como sinais de controle)
    // O controlador escreverá aqui qual entrada deve ir para cada saída
    sc_in<int> ort_table[NUM_PORTS];
    sc_in<bool> mux_enable_ctrl[NUM_PORTS];

    // Porta para o árbitro
    sc_fifo_out<PacketMetadata> request_out;

    //Configuração de Rede
    //NetworkConfig cfg;

    // Canais internos: Saída dos EBs -> Entrada dos MUXes
    sc_signal<Flit> eb_to_mux[NUM_PORTS];
    // Canais internos adicionais para Handshake EB <-> MUX
    sc_signal<bool> ack_matrix[NUM_PORTS][NUM_PORTS];
    // Sinal dummy para conectar o valid_out do EB que não usamos externamente
    sc_signal<bool> eb_valid_internal[NUM_PORTS];
    // Enable muxes
    sc_signal<bool> mux_enable[NUM_PORTS];
    sc_signal<bool> eb_to_mux_ack[NUM_PORTS][NUM_PORTS]; // EB escreve, MUX lê
    sc_signal<bool> mux_to_eb_ack[NUM_PORTS][NUM_PORTS]; // MUX escreve, EB lê
    // Instâncias
    ElasticBuffer* ebs[NUM_PORTS];
    OutputMUX* muxes[NUM_PORTS];

    sc_event event_novo_header;
    sc_out<sc_logic> stop_injector_out;


    Router(sc_module_name name, int _id) : sc_module(name), id(_id){
        for (int i = 0; i < NUM_PORTS; ++i) {
            ebs[i] = new ElasticBuffer(sc_gen_unique_name("eb"));
            muxes[i] = new OutputMUX(sc_gen_unique_name("mux"), id);
        }

        for (int i = 0; i < NUM_PORTS; ++i) {
            // Conexões EBs
            ebs[i]->clk(clk); ebs[i]->rst(rst);
            ebs[i]->in(in_ports[i]);
            ebs[i]->out(eb_to_mux[i]);
            ebs[i]->valid_out(eb_valid_internal[i]);
            ebs[i]->ready_out(ready_out[i]);
            ebs[i]->valid_in(in_valid[i]);

            // Conexões MUXes
            muxes[i]->selection(ort_table[i]);
            muxes[i]->out(out_ports[i]);
            muxes[i]->enable(mux_enable_ctrl[i]);
            muxes[i]->clk(clk); muxes[i]->rst(rst);
            muxes[i]->ready_in(ready_in[i]);
            muxes[i]->valid_out(valid_out[i]);

            // Conexões de Handshake (Seguro agora)
            for(int j = 0; j < NUM_PORTS; ++j){
                ebs[i]->ack_in[j](mux_to_eb_ack[i][j]); 
                muxes[i]->ack_to_eb[j](eb_to_mux_ack[i][j]);
                muxes[i]->in_valid[j](eb_valid_internal[j]);
                muxes[i]->in_ports[j](eb_to_mux[j]);
            }
        }


        SC_METHOD(log_in_ports);
        for(int i = 0; i < NUM_PORTS; ++i) {
            sensitive << in_ports[i];
        }
        dont_initialize();

        // Monitora o handshake
        SC_METHOD(monitor_handshake);
        for(int i = 0; i < NUM_PORTS; ++i) {
            sensitive << ready_in[i];
        }
        dont_initialize();

        // Mantem o seu request_arbitration
        SC_THREAD(request_arbitration);
        for(int i = 0; i < NUM_PORTS; ++i) {
            sensitive << eb_valid_internal[i];
        }
        dont_initialize();

        SC_METHOD(debug_packet_flow);
        sensitive << clk.pos(); // Roda a cada ciclo de clock
        dont_initialize();

    }

   void debug_packet_flow() {
        for(int i = 0; i < NUM_PORTS; i++) {
            if(eb_valid_internal[i].read()) {
                Flit f = eb_to_mux[i].read(); // Apenas leitura, não destrutiva para o EB
                
                if(f.is_header) {
                    event_novo_header.notify(SC_ZERO_TIME);
                    std::cout << "@" << sc_time_stamp() << " [Router " << id 
                            << "] Cabecalho recebido na porta " << i 
                            << " | Fluxo: " << f.flow_id 
                            << " | Destino: " << f.dst_id << std::endl;
                }
                if(f.is_tail && f.dst_id == id) {
                    std::cout << "@" << sc_time_stamp() << " MENSAGEM ENTREGUE NO DESTINO: " << id << std::endl;
                    stop_injector_out.write(SC_LOGIC_1);
                    // Agora sim, o pacote completo chegou.
                    // Pode disparar o stop aqui ou sinalizar o injetor.
                    //sc_stop(); 
                }
            }
        }
    }

    void check_connections() {
        std::cout << "Verificando conexoes do Router " << id << "..." << std::endl;
        // Checagem básica: Porta FIFO
        if (request_out.get_interface() == nullptr) 
            std::cout << "   [ERRO] request_out nao vinculada" << std::endl;

        for(int i = 0; i < NUM_PORTS; ++i) {
            if (in_ports[i].get_interface() == nullptr) std::cout << "   [ERRO] in_ports[" << i << "] nao vinculada" << std::endl;
            if (out_ports[i].get_interface() == nullptr) std::cout << "   [ERRO] out_ports[" << i << "] nao vinculada" << std::endl;
            if (ready_in[i].get_interface() == nullptr) std::cout << "   [ERRO] ready_in[" << i << "] nao vinculada" << std::endl;
            if (valid_out[i].get_interface() == nullptr) std::cout << "   [ERRO] valid_out[" << i << "] nao vinculada" << std::endl;
        }
    }

    void log_in_ports() {
        for(int i = 0; i < NUM_PORTS; ++i) {
            if (in_ports[i].event()) {
                std::cout << "@" << sc_time_stamp() << " [Router " << id 
                        << "] Dado novo na porta física " << i 
                        << " | ID: " << in_ports[i].read().id << std::endl;
            }
        }
    }

    void monitor_handshake() {
        for(int i = 0; i < NUM_PORTS; ++i) {
            if(ready_in[i].event()) {
                std::cout << "@" << sc_time_stamp() << " [Router " << id 
                        << "] MUDANCA: Porta " << i << " ready_in agora vale " 
                        << ready_in[i].read() << std::endl;
            }
        }
    }

    void request_arbitration() {
        while(true) {
            // Aguarda sinal de algum EB que tem header
            wait(event_novo_header); 

            for(int i = 0; i < NUM_PORTS; i++) {
                if(eb_valid_internal[i].read() && eb_to_mux[i].read().is_header) {
                    PacketMetadata meta;
                    meta.sender_id = id;
                    meta.receiver_id = eb_to_mux[i].read().dst_id;
                    meta.in_port = i;
                    
                    // Agora o write é BLOQUEANTE. Ele espera até ter espaço.
                    request_out.write(meta); 
                    std::cout << "@" << sc_time_stamp() << " [Router " << id 
                            << "] SUCESSO: Pedido enviado." << std::endl;
                }
            }
        }
    }
    
};

#endif