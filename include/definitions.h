#ifndef DEFINITIONS_H
#define DEFINITIONS_H

#include <iostream>
#include <vector>
#include <systemc.h>
#include "flit.h"

inline std::ostream& operator<<(std::ostream& os, const std::vector<int>& v) {
    os << "[ ";
    for (size_t i = 0; i < v.size(); ++i) {
        os << v[i] << (i < v.size() - 1 ? ", " : " ");
    }
    os << "]";
    return os;
}

struct PathWrapper {
    std::vector<int> path;

    // Construtores para facilitar o uso
    PathWrapper() {}
    PathWrapper(std::vector<int> p) : path(p) {}

    // O SystemC exige este operador para o sc_fifo::print funcionar
    friend std::ostream& operator<<(std::ostream& os, const PathWrapper& pw) {
        os << "[ ";
        for (int node : pw.path) {
            os << node << " ";
        }
        os << "]";
        return os;
    }
};

// Estrutura para estatísticas/metadados (usada para contagem e SDN)
struct PacketMetadata {
    int total_flits;
    int flow_id;
    int sender_id;
    int receiver_id;
    int in_port;
    sc_time tempo_requisicao;
    bool requisicao_registrada;

    // Construtor padrão (Obrigatório para canais SystemC)
    PacketMetadata() : total_flits(0), flow_id(0), sender_id(0), receiver_id(0), in_port(0),
                    tempo_requisicao(SC_ZERO_TIME), requisicao_registrada(false) {}

    bool operator==(const PacketMetadata& other) const {
        return (total_flits == other.total_flits &&
                flow_id == other.flow_id &&
                sender_id == other.sender_id &&
                receiver_id == other.receiver_id &&
                in_port == other.in_port &&
                tempo_requisicao == other.tempo_requisicao);
    }

    bool operator!=(const PacketMetadata& other) const {
        return !(*this == other);
    }

    PacketMetadata& operator=(const PacketMetadata& other) {
        if (this != &other) {
            total_flits = other.total_flits;
            flow_id = other.flow_id;
            sender_id = other.sender_id;
            receiver_id = other.receiver_id;
            in_port = other.in_port;
            tempo_requisicao = other.tempo_requisicao;
            requisicao_registrada = other.requisicao_registrada;
        }
        return *this;
    }
};

inline void sc_trace(sc_trace_file* tf, const PacketMetadata& meta, const std::string& name) {
    // Você pode decidir como o Metadata aparecerá no gráfico de ondas:
    // Opção A: Rastrear apenas um campo principal (se for um inteiro, por exemplo)
    sc_trace(tf, meta.flow_id, name + ".flow_id");
    sc_trace(tf, meta.sender_id, name + ".sender_id");
    sc_trace(tf, meta.receiver_id, name + ".receiver_id");
}

inline std::ostream& operator<<(std::ostream& os, const PacketMetadata& meta) {
    os << "PacketMetadata(Flow: " << meta.flow_id 
       << ", Src: " << meta.sender_id 
       << ", Dst: " << meta.receiver_id 
       << ", T_req: " << meta.tempo_requisicao
       << ", Flits: " << meta.total_flits << ")";
    return os;
}

inline void sc_trace(sc_trace_file* tf, const std::vector<int>& v, const std::string& name) {
    // Opcional: implementar rastreamento real se precisar ver o vetor no .vcd
}

struct PortSignals {
    // Sinais de SAÍDA (O Roteador escreve aqui para enviar ao vizinho)
    sc_signal<Flit>* out_data = nullptr;
    sc_signal<bool>* out_valid = nullptr;
    sc_signal<bool>* out_ready_in = nullptr; // Ready que vem do vizinho

    // Sinais de ENTRADA (O Roteador lê aqui o que vem do vizinho)
    sc_signal<Flit>* in_data = nullptr;
    sc_signal<bool>* in_valid = nullptr;
    sc_signal<bool>* in_ready_out = nullptr;
};

// Definição de constantes úteis
const int NUM_PORTS = 5; // N, S, L, O, Local
const int BUFFER_SIZE = 16;
const sc_time CLOCK_PERIOD(10, SC_NS); 
const sc_time LAT(1, SC_NS);

struct NetworkConfig {
    sc_time link_transit_latency;
    int max_retries;
    int retry_wait_ns;
    int packets_per_flow;
    int flits_per_packet;
    int idle_cycles;
};

struct TrafficEvent {
    int src;
    int dst;
    double start_time_ns;
    int flow_id;
};

enum ConfigAction {SETUP, RELEASE};

struct SwitchConfigCmd{
    ConfigAction action;
    int output_port; // Qual MUX de saída configurar (ex: porta que vai pro próximo nó)
    int input_port; // Qual porta de entrada selecionar (ex: porta que vem do nó anterior)
    bool enable;
    int flow_id;
};

inline std::ostream& operator<<(std::ostream& os, const SwitchConfigCmd& cmd) {
    os << "Cmd(action=" << cmd.action 
       << ", in=" << cmd.input_port 
       << ", out=" << cmd.output_port << ")";
    return os;
}

enum PortID {
    PORT_LOCAL = 0,
    PORT_NORTH = 1,
    PORT_SOUTH = 2,
    PORT_EAST = 3,
    PORT_WEST = 4
};

enum TrafficMode{
    DETERMINISTIC,
    UNIFORM,
    RANDOM
};

#endif