#!/usr/bin/env python3
"""
apply_link_length_patch.py -- latencia de link proporcional ao comprimento (OPCIONAL).

Novo parametro em network_params (padrao 0 = DESLIGADO, resultados identicos aos atuais):
    link_reach_tiles_per_cycle : tiles percorridos por ciclo (ex.: 4, 2, 1)

Quando > 0, o atraso do OutputMUX de cada porta conectada passa a ser
    link_transit_latency * max(1, ceil(comprimento / alcance))
com comprimento = distancia de Manhattan numa planta fixa W x W (W = sqrt(num_nodes),
no id = y*W + x). So o main.cpp muda (Router.h/OutputMUX.h/TopologyManager.h nao).

ATENCAO (limitacao conhecida): o wait(link_delay) fica dentro do laco do OutputMUX,
entao um link com atraso de k ciclos aceita 1 flit a cada k ciclos (menor vazao),
e nao "latencia k com vazao 1". Documentar na metodologia.

Uso:  py apply_link_length_patch.py --src . [--check]
Cria .bak; se qualquer ancora falhar (nao achada exatamente 1x), nada e escrito.
"""
import argparse, os, sys

EDITS = [
    # (arquivo, ancora, texto_antes, texto_depois)
    ("main.cpp", "#include <algorithm>", "", "\n#include <cmath>\n#include <cstdlib>"),
    ("main.cpp",
     "    net_cfg.link_transit_latency = CLOCK_PERIOD * link_transit_latency_cycles;", "",
     "\n    // Alcance do fio em tiles por ciclo (opcional). 0 = desligado: todo link usa\n"
     "    // link_transit_latency (comportamento anterior). Ver apply_link_length_patch.py.\n"
     "    const double link_reach_tiles_per_cycle =\n"
     "        cfg[\"network_params\"].value(\"link_reach_tiles_per_cycle\", 0.0);"),
    ("main.cpp",
     "                routers[i]->flit_out[p](*link_fifo);", "",
     "\n\n"
     "                // Latencia do link proporcional ao comprimento (opcional).\n"
     "                // Planta fixa W x W (id = y*W + x); comprimento = distancia de Manhattan.\n"
     "                if (link_reach_tiles_per_cycle > 0.0) {\n"
     "                    int W = static_cast<int>(std::lround(std::sqrt(static_cast<double>(num_nodes))));\n"
     "                    if (W < 1) W = 1;\n"
     "                    static bool warned_grid = false;\n"
     "                    if (!warned_grid && W * W != num_nodes) {\n"
     "                        std::cerr << \"AVISO: num_nodes=\" << num_nodes\n"
     "                                  << \" nao e quadrado perfeito; comprimento dos links assume grade \"\n"
     "                                  << W << \"x\" << W << std::endl;\n"
     "                        warned_grid = true;\n"
     "                    }\n"
     "                    int len = std::abs(i % W - vizinho % W) + std::abs(i / W - vizinho / W);\n"
     "                    int mult = std::max(1, static_cast<int>(std::ceil(len / link_reach_tiles_per_cycle - 1e-9)));\n"
     "                    routers[i]->muxes[p]->link_delay = net_cfg.link_transit_latency * mult;\n"
     "                }"),
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
    names = sorted({e[0] for e in EDITS})
    paths, texts, crlf = {}, {}, {}
    for n in names:
        hits = find_file(a.src, n)
        if len(hits) != 1:
            sys.exit(f"ERRO: esperava 1 arquivo '{n}' sob {a.src}, achei {len(hits)}: {hits}")
        raw = open(hits[0], "rb").read().decode("utf-8")
        paths[n], crlf[n] = hits[0], "\r\n" in raw
        texts[n] = raw.replace("\r\n", "\n")
        if "link_reach_tiles_per_cycle" in texts[n]:
            sys.exit(f"{n} ja contem link_reach_tiles_per_cycle. Nada feito.")
    errors = []
    for n, anchor, before, after in EDITS:
        c = texts[n].count(anchor)
        if c != 1:
            errors.append(f"  {n}: ancora aparece {c}x (esperado 1): {anchor!r}")
            continue
        texts[n] = texts[n].replace(anchor, before + anchor + after, 1)
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