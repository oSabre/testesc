#!/usr/bin/env python3
"""Patch da Fase 0.7/0.9: custo do plano de controle calibrado com o gem5.

Adiciona dois parametros opcionais em network_params (padroes preservam o comportamento antigo):
  dijkstra_pq_base_cycles (int, padrao 0): custo fixo por operacao de heap do Dijkstra, somado ao termo em log2.
  control_clock_ratio    (double, padrao 1.0): razao r = f_core / f_NoC. O custo final de cada chamada
                         (BFS ou Dijkstra), calculado em ciclos do core, vira ceil(custo / r) ciclos da NoC.

Arquivos alterados: definitions.h, main.cpp, ControlUnit.cpp (todos ou nenhum; cria .bak; preserva CRLF).
Uso: py apply_control_cost_patch.py --src <pasta do codigo>
"""
import argparse, glob, os, shutil, sys

PATCHES = {
 'definitions.h': [
  ('#include <map>\n#include <string>\n',
   '#include <map>\n#include <string>\n#include <cmath>\n'),
  ('    int dijkstra_edge_check_cycles = 1;\n',
   '    int dijkstra_edge_check_cycles = 1;\n'
   '    // Custo FIXO por operacao de heap do Dijkstra, somado ao termo em log2\n'
   '    // (calibrado no gem5, Fase 0.7). Padrao 0 = modelo antigo.\n'
   '    int dijkstra_pq_base_cycles = 0;\n'
   '    // Razao r = f_core / f_NoC do controlador. Os custos acima sao em ciclos do\n'
   '    // CORE; o tempo simulado de cada chamada e ceil(custo / r) ciclos da NoC.\n'
   '    // Padrao 1.0 = core e NoC na mesma frequencia (e nao altera o comportamento antigo).\n'
   '    double control_clock_ratio = 1.0;\n'
   '    long long scale_control_cycles(long long core_cycles) const {\n'
   '        if (control_clock_ratio == 1.0 || core_cycles <= 0) return core_cycles;\n'
   '        return static_cast<long long>(std::ceil(static_cast<double>(core_cycles) / control_clock_ratio - 1e-9));\n'
   '    }\n'),
 ],
 'main.cpp': [
  ('    net_cfg.dijkstra_edge_check_cycles    = cfg["network_params"].value("dijkstra_edge_check_cycles", net_cfg.dijkstra_edge_check_cycles);\n',
   '    net_cfg.dijkstra_edge_check_cycles    = cfg["network_params"].value("dijkstra_edge_check_cycles", net_cfg.dijkstra_edge_check_cycles);\n'
   '    net_cfg.dijkstra_pq_base_cycles       = cfg["network_params"].value("dijkstra_pq_base_cycles", net_cfg.dijkstra_pq_base_cycles);\n'
   '    net_cfg.control_clock_ratio           = cfg["network_params"].value("control_clock_ratio", net_cfg.control_clock_ratio);\n'
   '    if (!(net_cfg.control_clock_ratio > 0.0)) {\n'
   '        std::cerr << "ERRO: control_clock_ratio deve ser > 0." << std::endl;\n'
   '        return 1;\n'
   '    }\n'),
 ],
 'ControlUnit.cpp': [
  ('        wait(CLOCK_PERIOD * bcost);\n',
   '        wait(CLOCK_PERIOD * cfg->scale_control_cycles(bcost));\n'),
  ('        return std::max<long long>(1, c);\n',
   '        return std::max<long long>(1, c) + cfg->dijkstra_pq_base_cycles;\n'),
  ('    wait(CLOCK_PERIOD * custo_ciclos);\n',
   '    wait(CLOCK_PERIOD * cfg->scale_control_cycles(custo_ciclos));\n'),
 ],
}
MARK = {'definitions.h': 'control_clock_ratio', 'main.cpp': 'control_clock_ratio', 'ControlUnit.cpp': 'scale_control_cycles'}

def find(src, name):
    hits = [p for p in glob.glob(os.path.join(src, '**', name), recursive=True) if not p.endswith('.bak')]
    if len(hits) != 1:
        sys.exit(f"ERRO: esperava 1 arquivo {name} em {src}, achei {len(hits)}: {hits}")
    return hits[0]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--src', default='.'); ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()
    new = {}
    for name, edits in PATCHES.items():
        path = find(a.src, name)
        raw = open(path, 'rb').read().decode('utf-8', errors='surrogateescape')
        crlf = '\r\n' in raw
        txt = raw.replace('\r\n', '\n')
        if MARK[name] in txt:
            print(f"{name}: ja aplicado, nada a fazer"); continue
        for old, rep in edits:
            n = txt.count(old)
            if n != 1:
                sys.exit(f"ERRO em {name}: ancora encontrada {n} vez(es) (esperado 1):\n{old}\nNada foi alterado.")
            txt = txt.replace(old, rep)
        new[path] = (txt.replace('\n', '\r\n') if crlf else txt)
    if a.dry:
        print("dry-run OK; arquivos que seriam alterados:", list(new)); return
    for path, txt in new.items():
        shutil.copy2(path, path + '.bak')
        open(path, 'wb').write(txt.encode('utf-8', errors='surrogateescape'))
        print("alterado:", path, "(backup .bak)")
    print("pronto. Recompile e rode a regressao (parametros novos desligados => resultado identico).")

if __name__ == '__main__': main()