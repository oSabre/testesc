#ifndef FLIT_H
#define FLIT_H

#include <systemc.h>
#include <iostream>
// Estrutura do dado básico que flui pelo barramento
struct Flit {
    int id = 0;
    int data = 0;
    bool is_header = false;
    bool is_tail = false;
    int flow_id = 0;
    sc_time timestamp = SC_ZERO_TIME;
    int hop_count = 0;
    int src_id = 0;
    int dst_id = 0;
    bool valid = false;
    bool ready = false;

    // Construtor padrão (obrigatório para o SystemC)
    Flit() {}

    // Operador de igualdade (essencial para o sc_signal)
    bool operator==(const Flit& other) const {
        return (id == other.id &&
                data == other.data &&
                is_header == other.is_header &&
                is_tail == other.is_tail &&
                flow_id == other.flow_id &&
                timestamp == other.timestamp &&
                hop_count == other.hop_count &&
                src_id == other.src_id &&
                dst_id == other.dst_id &&
                valid == other.valid &&
                ready == other.ready);
    }

    // Operador de desigualdade
    bool operator!=(const Flit& other) const {
        return !(*this == other);
    }

    void print(std::ostream& os = std::cout) const {
        os << "Flit(id=" << id << ")";
    }

};

// Sobrecarga opcional para facilitar o debug com cout
inline std::ostream& operator<<(std::ostream& os, const Flit& f) {
    os << "Flit(id=" << f.id << ", dst=" << f.dst_id << ")";
    return os;
}

// OBRIGATÓRIO: O SystemC precisa desta função para rastrear seu tipo customizado
inline void sc_trace(sc_trace_file* tf, const Flit& f, const std::string& name) {
    sc_trace(tf, f.id, name + ".id");
    sc_trace(tf, f.data, name + ".data");
}

#endif