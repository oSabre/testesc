#!/usr/bin/env python3
"""
apply_trace_patch.py -- adiciona rastreamento (trace) opcional ao simulador.

Nao altera nenhum resultado: com trace desligado (padrao) o comportamento e o
tempo simulado sao identicos. O trace so escreve em arquivo (nunca usa wait()).

Uso (na pasta do projeto ou passando --src):
    python3 apply_trace_patch.py --src .          # aplica
    python3 apply_trace_patch.py --src . --check  # so verifica as ancoras

Cria um .bak de cada arquivo alterado. Se qualquer ancora nao for encontrada
(exatamente 1 vez), NADA e escrito.

Parametros novos em network_params (nada muda se ausentes):
    trace_flow_ids : inteiro | "15,47" | "all" | -1 (todos)
    trace_file     : caminho ABSOLUTO do log (o ga_diag roda em pasta temporaria)
"""
import argparse, os, re, sys

TRACE_DEFS = r'''// ---- Rastreamento opcional (trace). Desligado por padrao. ----
// Ligado por network_params.trace_flow_ids + trace_file (ver main.cpp).
// Nao usa wait(): nao altera o tempo simulado.
#include <set>
#include <fstream>
#include <sstream>
inline std::set<int>& trace_flow_ids() { static std::set<int> s; return s; }  // -1 = todos
inline std::ofstream& trace_out() { static std::ofstream f; return f; }
inline bool trace_enabled() { return trace_out().is_open(); }
inline bool trace_flow(int id) {
    return trace_enabled() && (trace_flow_ids().count(id) > 0 || trace_flow_ids().count(-1) > 0);
}
// Porta de entrada em que cada OutputMUX esta bloqueado lendo (-1 = nenhuma).
inline std::map<std::string, int>& mux_blocked_port() { static std::map<std::string, int> m; return m; }
inline std::string trace_route_str(const std::vector<int>& r) {
    std::ostringstream os;
    for (size_t i = 0; i < r.size(); ++i) os << r[i] << (i + 1 < r.size() ? "->" : "");
    return os.str();
}
#define TRACE_LOG(expr) do { if (trace_enabled()) { trace_out() << "@" << sc_core::sc_time_stamp() << " " << expr << std::endl; } } while (0)
#define TRACE_FLOW(fid, expr) do { if (trace_flow(fid)) { TRACE_LOG(expr); } } while (0)

'''

MAIN_BLOCK = r'''
    // ---- trace (opcional) ----
    {
        const auto& np_t = cfg["network_params"];
        if (np_t.contains("trace_flow_ids")) {
            const auto& t = np_t["trace_flow_ids"];
            if (t.is_number_integer()) {
                trace_flow_ids().insert(t.get<int>());
            } else if (t.is_array()) {
                for (const auto& x : t) trace_flow_ids().insert(x.get<int>());
            } else if (t.is_string()) {
                std::string s = t.get<std::string>();
                if (s == "all") {
                    trace_flow_ids().insert(-1);
                } else {
                    std::stringstream ss(s);
                    std::string tok;
                    while (std::getline(ss, tok, ',')) {
                        if (!tok.empty()) trace_flow_ids().insert(std::stoi(tok));
                    }
                }
            }
        }
        if (!trace_flow_ids().empty()) {
            std::string tf = np_t.value("trace_file", std::string("trace_flows.log"));
            trace_out().open(tf, std::ios::out | std::ios::trunc);
        }
    }
'''

# (arquivo, ancora, texto_antes, texto_depois)
EDITS = [
    ("definitions.h", "inline std::ostream& operator<<(std::ostream& os, const std::vector<int>& v) {",
     TRACE_DEFS, ""),

    ("main.cpp", 'tm->set_reserve_dst(cfg["network_params"].value("reserve_dst_port", false));',
     "", MAIN_BLOCK),

    ("ControlUnit.cpp", "route = calculate_dijkstra(req.sender_id, req.receiver_id);", "",
     '\n            TRACE_FLOW(req.flow_id, "[CU " << name() << "] flow " << req.flow_id << " " << req.sender_id << "->" << req.receiver_id'
     ' << " falhas_ate_agora=" << retry_count << " rota=" << trace_route_str(route));'),
    ("ControlUnit.cpp", "path_allocated = tm->try_allocate_path(route);", "",
     '\n            TRACE_FLOW(req.flow_id, "[CU " << name() << "] flow " << req.flow_id << " try_allocate_path=" << path_allocated);'),
    ("ControlUnit.cpp", "parent_sdn->configure_path_hardware(route, req.flow_id);", "",
     '\n                TRACE_FLOW(req.flow_id, "[CU " << name() << "] flow " << req.flow_id << " comandos SETUP enviados");'),
    ("ControlUnit.cpp", "parent_sdn->wait_for_route_ack(req.flow_id, route);", "",
     '\n                TRACE_FLOW(req.flow_id, "[CU " << name() << "] flow " << req.flow_id << " ACK de SETUP de todos os roteadores");'),
    ("ControlUnit.cpp", "path_ready_out.write(req.flow_id);", "",
     '\n                TRACE_FLOW(req.flow_id, "[CU " << name() << "] flow " << req.flow_id << " path_ready enviado");'),

    ("SDN_Controller.cpp", "router_config_out[current_node].write(cmd);", "",
     '\n        TRACE_FLOW(flow_id, "[SDN] SETUP escrito: flow " << flow_id << " roteador " << current_node << " in=" << in_port << " out=" << out_port);'),
    ("SDN_Controller.cpp", "router_config_out[current_router].write(cmd);", "",
     '\n                TRACE_FLOW(flow_id, "[SDN] RELEASE escrito: flow " << flow_id << " roteador " << current_router << " in=" << in_port << " out=" << out_port);'),
    ("SDN_Controller.cpp", "int flow_id = teardown_in.read();", "",
     '\n        TRACE_FLOW(flow_id, "[SDN] teardown solicitado: flow " << flow_id);'),
    ("SDN_Controller.cpp", "tm->release_path(route);", "",
     '\n            TRACE_FLOW(flow_id, "[SDN] release_path: links liberados flow " << flow_id);'),
    ("SDN_Controller.cpp", "int flow_id = router_config_ack_in[router_index].read();", "",
     '\n        TRACE_FLOW(flow_id, "[SDN] ACK do roteador " << router_index << " flow " << flow_id);'),

    ("LocalAgent.h", "mux_sel[cmd.output_port].write(cmd.input_port);",
     '''if (trace_enabled()) {
                        std::string rn = get_parent_object() ? std::string(get_parent_object()->name()) : std::string("?");
                        std::string mn = rn + ".mux_" + std::to_string(cmd.output_port);
                        auto it_b = mux_blocked_port().find(mn);
                        int bp = (it_b == mux_blocked_port().end()) ? -1 : it_b->second;
                        TRACE_FLOW(cmd.flow_id, "[LocalAgent " << rn << "] SETUP aplicado flow " << cmd.flow_id
                                   << " in=" << cmd.input_port << " out=" << cmd.output_port
                                   << " (mux esperando porta " << bp << ")");
                    }
                    ''', ""),
    ("LocalAgent.h", "mux_enable[cmd.output_port].write(false);",
     '''if (trace_enabled()) {
                        std::string rn = get_parent_object() ? std::string(get_parent_object()->name()) : std::string("?");
                        TRACE_FLOW(cmd.flow_id, "[LocalAgent " << rn << "] RELEASE aplicado flow " << cmd.flow_id
                                   << " in=" << cmd.input_port << " out=" << cmd.output_port);
                    }
                    ''', ""),

    ("input_buffer.h", "current_target = target_port.read();", "",
     '\n            TRACE_FLOW(f.flow_id, "[InputBuffer " << name() << "] flit " << f.flit_id << " pkt " << f.packet_id'
     ' << " flow " << f.flow_id << " alvo=" << current_target << (current_target < 0 ? "  !! ROTA NAO CONFIGURADA" : ""));'),

    ("TrafficInjector.cpp", "stats->record_request(event.flow_id, sc_time_stamp());", "",
     '\n    TRACE_FLOW(event.flow_id, "[Injector] flow " << event.flow_id << " " << event.src << "->" << event.dst << " pede rota");'),
    ("TrafficInjector.cpp", "stats->record_setup(event.flow_id, sc_time_stamp());", "",
     '\n    TRACE_FLOW(event.flow_id, "[Injector] flow " << event.flow_id << " caminho pronto, inicia envio");'),
    ("TrafficInjector.cpp", "wait_for_flow_completion(event.flow_id);",
     'TRACE_FLOW(event.flow_id, "[Injector] flow " << event.flow_id << " todos os flits injetados, aguarda entrega");\n    ', ""),
    ("TrafficInjector.cpp", "stats->record_finish(event.flow_id, sc_time_stamp());", "",
     '\n    TRACE_FLOW(event.flow_id, "[Injector] flow " << event.flow_id << " entrega confirmada");'),
    ("TrafficInjector.cpp", "Flit flit = data_in[node_id].read();", "",
     '\n        TRACE_FLOW(flit.flow_id, "[Injector] no " << node_id << " recebeu flit " << flit.flit_id << " pkt " << flit.packet_id'
     ' << " flow " << flit.flow_id << (flit.is_tail ? " TAIL" : ""));'),
    ("TrafficInjector.cpp", "data_out[event.src].write(flit);", "",
     '\n            TRACE_FLOW(event.flow_id, "[Injector] flow " << event.flow_id << " injetou flit " << f << " pkt " << p << " em " << event.src);'),
    ("TrafficInjector.cpp", "teardown_to_sdn.write(flow_id);", "",
     '\n    TRACE_FLOW(flow_id, "[Injector] flow " << flow_id << " pede teardown");'),
]


def find_file(src, name):
    hits = []
    for root, _, files in os.walk(src):
        if any(p in root for p in ("/.git", "/runs", "/__pycache__")):
            continue
        if name in files:
            hits.append(os.path.join(root, name))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=".")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    names = sorted({e[0] for e in EDITS} | {"OutputMUX.h"})
    paths, texts, crlf = {}, {}, {}
    for n in names:
        hits = find_file(a.src, n)
        if len(hits) != 1:
            sys.exit(f"ERRO: esperava 1 arquivo '{n}' sob {a.src}, achei {len(hits)}: {hits}")
        raw = open(hits[0], "rb").read().decode("utf-8")
        paths[n] = hits[0]
        crlf[n] = "\r\n" in raw
        texts[n] = raw.replace("\r\n", "\n")
        if "TRACE_FLOW" in texts[n] or "trace_enabled" in texts[n]:
            sys.exit(f"{n} ja contem o patch de trace. Nada feito.")

    errors = []
    for n, anchor, before, after in EDITS:
        c = texts[n].count(anchor)
        if c != 1:
            errors.append(f"  {n}: ancora aparece {c}x (esperado 1): {anchor!r}")
            continue
        texts[n] = texts[n].replace(anchor, before + anchor + after, 1)

    # OutputMUX.h: duas variantes conhecidas.
    t = texts["OutputMUX.h"]
    if "nb_read(" in t:
        # variante com espera por evento + nb_read (reavalia a config quando sel muda)
        steps = [
            ("if (!enable.read()) {", "",
             "\n                if (trace_enabled()) { mux_blocked_port()[std::string(name())] = -1; }"),
            ("bool reconfigured = false;",
             "if (trace_enabled()) { mux_blocked_port()[std::string(name())] = port; }\n            ", ""),
            ("flit_in[port].nb_read(f);", "",
             "\n            if (trace_enabled()) {\n"
             "                mux_blocked_port()[std::string(name())] = -1;\n"
             "                TRACE_FLOW(f.flow_id, \"[MUX \" << name() << \"] flit \" << f.flit_id << \" pkt \" << f.packet_id"
             " << \" flow \" << f.flow_id << \" lido da porta \" << port);\n"
             "            }"),
        ]
        for anchor, bef, aft in steps:
            if t.count(anchor) != 1:
                errors.append(f"  OutputMUX.h: ancora aparece {t.count(anchor)}x (esperado 1): {anchor!r}")
            else:
                t = t.replace(anchor, bef + anchor + aft, 1)
        texts["OutputMUX.h"] = t
    else:
        # variante antiga: Flit x = flit_in[p].read();
        mux_re = re.compile(r"(?P<ind>[ \t]*)Flit\s+(?P<v>\w+)\s*=\s*(?P<arr>flit_in)\[(?P<p>\w+)\]\s*\.read\(\)\s*;")
        m = list(mux_re.finditer(t))
        if len(m) != 1:
            errors.append(f"  OutputMUX.h: nem nb_read nem 'Flit x = flit_in[p].read();' (achei {len(m)}x o segundo)")
        else:
            mm = m[0]
            v, pp, ind = mm.group("v"), mm.group("p"), mm.group("ind")
            new = (ind + "if (trace_enabled()) { mux_blocked_port()[std::string(name())] = " + pp + "; }\n"
                   + mm.group(0) + "\n"
                   + ind + "if (trace_enabled()) {\n"
                   + ind + "    mux_blocked_port()[std::string(name())] = -1;\n"
                   + ind + "    TRACE_FLOW(" + v + ".flow_id, \"[MUX \" << name() << \"] flit \" << " + v + ".flit_id << \" pkt \" << " + v + ".packet_id"
                   + " << \" flow \" << " + v + ".flow_id << \" lido da porta \" << " + pp + ");\n"
                   + ind + "}")
            texts["OutputMUX.h"] = t[:mm.start()] + new + t[mm.end():]

    if errors:
        sys.exit("ERRO: ancoras nao encontradas (nada foi escrito):\n" + "\n".join(errors) +
                 "\nMande os arquivos citados para eu ajustar o patch.")

    if a.check:
        print("OK: todas as ancoras foram encontradas 1x. Nada escrito (--check).")
        return
    for n in names:
        p = paths[n]
        if not os.path.exists(p + ".bak"):
            open(p + ".bak", "wb").write(open(p, "rb").read())
        out = texts[n].replace("\n", "\r\n") if crlf[n] else texts[n]
        open(p, "wb").write(out.encode("utf-8"))
        print("patch aplicado:", p)
    print("\nFeito. Recompile: make clean && make main.exe")


if __name__ == "__main__":
    main()