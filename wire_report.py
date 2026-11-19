#!/usr/bin/env python3
"""
wire_report.py -- fio total, comprimento e grau de topologias (orcamento: links + fio).

Entradas (qualquer mistura; globs aceitos):
  * config JSON do simulador (campo "topology": [{u,v}, ...])
  * best_edges.json (lista de pares [u,v])
  * pasta de execucao do GA (usa <pasta>/best_edges.json)
Planta fixa W x W (id = y*W + x), W = sqrt(nos); comprimento = Manhattan.

Uso:  py wire_report.py runs/*  configs/configs_ciclos/config_*_64.json --out wire_report.csv
"""
import argparse, csv, glob, json, os, sys
from collections import Counter

def load_edges(path):
    if os.path.isdir(path):
        path = os.path.join(path, "best_edges.json")
    with open(path) as f:
        d = json.load(f)
    if isinstance(d, dict) and "topology" in d:
        return [(min(l["u"], l["v"]), max(l["u"], l["v"])) for l in d["topology"]]
    if isinstance(d, list):
        return [(min(u, v), max(u, v)) for u, v in d]
    raise ValueError("formato nao reconhecido")

def report(name, edges, nodes=None):
    n = nodes or (max(max(e) for e in edges) + 1)
    W = int(round(n ** 0.5))
    if W * W != n:
        raise ValueError(f"{name}: {n} nos nao e quadrado perfeito")
    lens = [abs(u % W - v % W) + abs(u // W - v // W) for u, v in edges]
    deg = Counter()
    for u, v in edges:
        deg[u] += 1; deg[v] += 1
    mesh_links = 2 * W * (W - 1)
    L, tot = len(edges), sum(lens)
    hist = Counter(lens)
    return {"nome": name, "nos": n, "links": L, "links_vs_mesh": round(L / mesh_links, 3),
            "fio_total": tot, "fio_vs_mesh": round(tot / mesh_links, 3),
            "fio_por_link": round(tot / L, 3), "comp_max": max(lens),
            "links_comp1": hist[1], "links_longos(>1)": L - hist[1],
            "links_comp>=4": sum(c for k, c in hist.items() if k >= 4),
            "grau_max": max(deg.values()), "grau_min": min(deg.get(i, 0) for i in range(n)),
            "cabe_m1.5": tot <= 1.5 * L, "cabe_m2": tot <= 2 * L, "cabe_m3": tot <= 3 * L}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--nodes", type=int, default=None)
    ap.add_argument("--out", default="wire_report.csv")
    a = ap.parse_args()
    rows = []
    for pat in a.paths:
        for p in sorted(glob.glob(pat)) or [pat]:
            try:
                name = os.path.basename(p.rstrip("/\\"))
                if os.path.isfile(p) and name == "best_edges.json":
                    name = os.path.basename(os.path.dirname(os.path.abspath(p)))
                rows.append(report(name, load_edges(p), a.nodes))
            except Exception as e:
                print(f"[pulado] {p}: {e}", file=sys.stderr)
    if not rows:
        sys.exit("nenhuma topologia lida")
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    cols = ["nome", "links", "fio_total", "fio_vs_mesh", "fio_por_link", "comp_max",
            "links_longos(>1)", "grau_max", "cabe_m1.5", "cabe_m2", "cabe_m3"]
    wid = {c: max(len(c), max(len(str(r[c])) for r in rows)) for c in cols}
    print(" ".join(c.ljust(wid[c]) for c in cols))
    for r in rows:
        print(" ".join(str(r[c]).ljust(wid[c]) for c in cols))
    print(f"\n-> {a.out}")

if __name__ == "__main__":
    main()