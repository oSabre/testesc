#!/usr/bin/env python3
"""Custo modelado de controle (BFS e Dijkstra) por topologia candidata.

Usa o kernel do Fase 0.7 compilado NATIVAMENTE (sem gem5; so os contadores importam) para obter
nos visitados, operacoes de fila/heap, soma de log2 e arestas, e aplica os coeficientes calibrados:
  BFS      = dispatch + init*N + pq_op*ops + edge*arestas
  Dijkstra = dispatch + init*N + sum_ops[max(1, round(pq_op*log2(tam_fila))) + base] + edge*arestas  (igual ao simulador)
Objetivo: testar se o custo por chamada do Dijkstra (e do BFS) depende da topologia (mesh x irregulares).

Uso (pasta do simulador; kernel_routing.cpp e make_topologies.py na mesma pasta que este script ou em --kernel):
  python3 custo_por_topologia.py --run-dirs "runs/bfs_*_cu16_*" \
      --extra mesh:configs/configs_ciclos/config_mesh_64.json \
      --extra smallworld:configs/configs_ciclos/config_irregular_smallworld_64.json \
      --pairs 400 --busy 0 25 --out custo_topologias
Saidas: <out>.csv (por topologia e ocupacao) e tabela no terminal (delta% contra a mesh).
"""
import argparse, csv, glob, json, math, os, subprocess, sys, tempfile

def find_links(obj):
    if isinstance(obj, list) and obj and all(isinstance(d, dict) and 'u' in d and 'v' in d for d in obj):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            r = find_links(v)
            if r: return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_links(v)
            if r: return r
    return None

def load_edges(path):
    d = json.load(open(path))
    if isinstance(d, list) and d and isinstance(d[0], (list, tuple)):
        return sorted({tuple(sorted((int(a), int(b)))) for a, b in d})
    links = find_links(d)
    if links is None:
        raise ValueError("sem links em " + path)
    return sorted({tuple(sorted((int(l['u']), int(l['v'])))) for l in links})

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dirs", nargs="*", default=[], help="globs de pastas com best_edges.json")
    ap.add_argument("--extra", action="append", default=[], help="nome:config.json")
    ap.add_argument("--n", type=int, default=64)
    ap.add_argument("--pairs", type=int, default=400)
    ap.add_argument("--busy", type=int, nargs="+", default=[0, 25])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--kernel", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--out", default="custo_topologias")
    ap.add_argument("--ref", default="mesh")
    ap.add_argument("--bfs", type=int, nargs=4, default=[129, 1, 39, 1], metavar=("DISP", "INIT", "PQOP", "EDGE"))
    ap.add_argument("--dij", type=int, nargs=5, default=[227, 5, 45, 11, 1], metavar=("DISP", "INIT", "BASE", "PQOP", "EDGE"))
    a = ap.parse_args()

    src = os.path.join(a.kernel, "kernel_routing_cost.cpp")
    exe = os.path.join(tempfile.gettempdir(), "kernel_native_%d" % os.getuid())
    if not os.path.exists(exe) or os.path.getmtime(exe) < os.path.getmtime(src):
        subprocess.check_call(["g++", "-O2", "-std=c++17", "-DPQ_OP=%d" % a.dij[3], src, "-o", exe])

    topos = []  # (nome, arestas)
    for pat in a.run_dirs:
        for d in sorted(glob.glob(pat)):
            p = os.path.join(d, "best_edges.json")
            if os.path.exists(p):
                topos.append((os.path.basename(d.rstrip("/")), load_edges(p)))
    for e in a.extra:
        name, path = e.split(":", 1)
        topos.append((name, load_edges(path)))
    if not topos:
        sys.exit("nenhuma topologia encontrada")

    rows = []
    tmp = tempfile.mkdtemp()
    for name, edges in topos:
        tp = os.path.join(tmp, name + ".txt")
        with open(tp, "w") as f:
            f.write("%d %d\n" % (a.n, len(edges)))
            for u, v in edges: f.write("%d %d\n" % (u, v))
        for busy in a.busy:
            outc = os.path.join(tmp, "%s_%d.csv" % (name, busy))
            subprocess.check_call([exe, tp, outc, str(a.pairs), str(a.seed), str(busy)], stdout=subprocess.DEVNULL)
            acc = {"bfs": [], "dijkstra": []}
            for r in csv.DictReader(open(outc)):
                N = int(r["N"]); ops = int(r["ops"]); ed = int(r["edges"]); l2 = float(r["log2sum"])
                if r["algo"] == "bfs":
                    cost = a.bfs[0] + a.bfs[1] * N + a.bfs[2] * ops + a.bfs[3] * ed
                else:
                    cost = a.dij[0] + a.dij[1] * N + a.dij[2] * ops + int(r["qcal"]) + a.dij[4] * ed
                acc[r["algo"]].append((cost, int(r["visited"]), ops, int(r["pushes"]), ed, int(r["path_len"])))
            for algo, v in acc.items():
                n = len(v); m = lambda i: sum(x[i] for x in v) / n
                mc = m(0); sd = math.sqrt(sum((x[0] - mc) ** 2 for x in v) / max(1, n - 1))
                rows.append(dict(topology=name, L=len(edges), busy_pct=busy, algo=algo, cost_mean=mc, cost_sd=sd,
                                 visited=m(1), ops=m(2), pushes=m(3), edges=m(4), path_len=m(5), pairs=n))

    with open(a.out + ".csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    print("Custo modelado por chamada (ciclos do core, r=1), %d pares por topologia; delta%% contra '%s'" % (a.pairs, a.ref))
    for algo in ("bfs", "dijkstra"):
        for busy in a.busy:
            sel = [r for r in rows if r["algo"] == algo and r["busy_pct"] == busy]
            ref = next((r for r in sel if r["topology"] == a.ref), None)
            print("\n== %s, links ocupados %d%% ==" % (algo, busy))
            print("%-40s %4s %9s %7s %8s %8s %7s %6s" % ("topologia", "L", "custo", "delta%", "visit", "ops", "push", "path"))
            for r in sorted(sel, key=lambda r: r["cost_mean"]):
                dl = (r["cost_mean"] / ref["cost_mean"] - 1) * 100 if ref else float("nan")
                print("%-40s %4d %9.0f %+7.1f %8.1f %8.1f %7.1f %6.2f" % (r["topology"][:40], r["L"], r["cost_mean"], dl,
                      r["visited"], r["ops"], r["pushes"], r["path_len"]))
            others = [r for r in sel if r["topology"] != a.ref and not r["topology"].startswith("smallworld")]
            if ref and others:
                mean_o = sum(r["cost_mean"] for r in others) / len(others)
                print("   media das treinadas: %.0f (%+.1f%% vs %s)" % (mean_o, (mean_o / ref["cost_mean"] - 1) * 100, a.ref))
    print("\nCSV: %s.csv  (custo no simulador depende tambem de retries; aqui so o custo do calculo por chamada)" % a.out)

if __name__ == "__main__":
    main()