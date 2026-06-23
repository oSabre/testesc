#ifndef FLIT_H
#define FLIT_H

#include <systemc.h>
#include <iostream>
// Estrutura do dado básico que flui pelo barramento
struct Flit {
    int flit_id = 0;
    int packet_id = 0;
    int flow_id = 0;
    int data = 0;

    bool is_header = false;
    bool is_tail = false;

    sc_time timestamp = SC_ZERO_TIME;
    int hop_count = 0;
    int src_id = 0;
    int dst_id = 0;

    // Construtor padrão (obrigatório para o SystemC)
    Flit() {}

    // Operador de igualdade (essencial para o sc_signal)
    bool operator==(const Flit& other) const {
        return (flit_id == other.flit_id &&
                packet_id == other.packet_id &&
                flow_id == other.flow_id &&
                data == other.data &&
                is_header == other.is_header &&
                is_tail == other.is_tail &&
                timestamp == other.timestamp &&
                hop_count == other.hop_count &&
                src_id == other.src_id &&
                dst_id == other.dst_id);
    }

    // Operador de desigualdade
    bool operator!=(const Flit& other) const {
        return !(*this == other);
    }

    void print(std::ostream& os = std::cout) const {
        os << "Flit(flow=" << flow_id << ", pkt=" << packet_id << ", flit=" << flit_id << ")";
    }

};

// Sobrecarga opcional para facilitar o debug com cout
inline std::ostream& operator<<(std::ostream& os, const Flit& f) {
    os << "Flit[F:" << f.flow_id << "|P:" << f.packet_id << "|f:" << f.flit_id 
       << (f.is_header ? "|HEAD" : "") 
       << (f.is_tail ? "|TAIL" : "") << "]";
    return os;
}

// OBRIGATÓRIO: O SystemC precisa desta função para rastrear seu tipo customizado
inline void sc_trace(sc_trace_file* tf, const Flit& f, const std::string& name) {
    sc_trace(tf, f.flit_id, name + ".flit_id");
    sc_trace(tf, f.packet_id, name + ".packet_id");
    sc_trace(tf, f.flow_id, name + ".flow_id");
    sc_trace(tf, f.is_header, name + ".is_header");
    sc_trace(tf, f.is_tail, name + ".is_tail");
}

#endif