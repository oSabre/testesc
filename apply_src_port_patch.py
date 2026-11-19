#!/usr/bin/env python3
"""
apply_src_port_patch.py -- reserva a porta de INJECAO (origem) como recurso,
espelhando reserve_dst_port. Corrige o fluxo preso causado por dois fluxos da
MESMA origem: o RELEASE do fluxo antigo apaga o buffer_target[LOCAL] que o
SETUP do fluxo novo acabou de escrever.

Novo parametro (network_params.reserve_src_port, padrao false = nada muda).

Uso:  py apply_src_port_patch.py --src . [--check]
Cria .bak; se qualquer ancora falhar (nao encontrada exatamente 1x), nada e escrito.
"""
import argparse, os, sys

EDITS = [
    ("TopologyManager.h", "    bool reserve_dst = false;", "",
     "\n    bool reserve_src = false;           // porta de injecao (origem) como recurso\n"
     "    std::map<int, bool> src_busy;"),
    ("TopologyManager.h", "    void set_reserve_dst(bool b) { reserve_dst = b; }", "",
     "\n    void set_reserve_src(bool b) { reserve_src = b; }"),
    ("TopologyManager.h", "        // 0. (opcional) porta de ejecao do destino precisa estar livre",
     "        // 0a. (opcional) porta de injecao da origem precisa estar livre: sem isso, o RELEASE\n"
     "        // do fluxo anterior da mesma origem apaga o buffer_target[LOCAL] do fluxo novo.\n"
     "        if (reserve_src && src_busy[path.front()]) {\n"
     "            topo_mutex.unlock();\n"
     "            return false;\n"
     "        }\n\n", ""),
    ("TopologyManager.h", "        if (reserve_dst) dst_busy[path.back()] = true;", "",
     "\n        if (reserve_src) src_busy[path.front()] = true;"),
    ("TopologyManager.h", "        if (reserve_dst && !path.empty()) dst_busy[path.back()] = false;", "",
     "\n        if (reserve_src && !path.empty()) src_busy[path.front()] = false;"),
    ("main.cpp", 'tm->set_reserve_dst(cfg["network_params"].value("reserve_dst_port", false));', "",
     '\n    tm->set_reserve_src(cfg["network_params"].value("reserve_src_port", false));'),
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
        if "reserve_src" in texts[n]:
            sys.exit(f"{n} ja contem reserve_src. Nada feito.")
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