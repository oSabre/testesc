#!/usr/bin/env python3
"""
analyze_topology.py -- explica POR QUE uma topologia vence num padrao de trafego.
Para cada config e padrao mostra:
  * saltos medios dos pares (src,dst) do padrao e fracao de pares com link DIRETO
  * nos 'extraidos' pelo Dijkstra ate chegar ao destino (aprox.: o custo de
    controle depende disso por causa do 'if (u==dst) break')
  * grau (min/max) e numero de links de longo alcance (fora da grade)
Uso: py analyze_topology.py mesh:configs/configs_ciclos/config_mesh_64.json \
        ga:runs/bit_reversal_cu16_ga_random/best_config.json  [--patterns bit_reversal butterfly]
"""
import argparse, json, statistics as st
from collections import deque, defaultdict


def load(p):
    return json.load(open(p))["topology"]


def perm_pairs(pattern, n=64):
    k = n.bit_length() - 1
    if pattern == "bit_reversal":
        f = lambda i: int(format(i, "0%db" % k)[::-1], 2)
    else:
        f = lambda i: ((i << 1) & (n - 1)) | (i >> (k - 1))
    return [(i, f(i)) for i in range(n) if f(i) != i]


def analyze(links, pattern, n=64):
    adj = defaultdict(list)
    for l in links:
        adj[l["u"]].append(l["v"]); adj[l["v"]].append(l["u"])
    dist = {}
    for s in range(n):
        d = {s: 0}; q = deque([s])
        while q:
            u = q.popleft()
            for v in adj[u]:
                if v not in d:
                    d[v] = d[u] + 1; q.append(v)
        dist[s] = d
    pairs = perm_pairs(pattern, n) if pattern != "uniform" else [(a, b) for a in range(n) for b in range(n) if a != b]
    hops = [dist[a][b] for a, b in pairs]
    direct = sum(1 for h in hops if h == 1) / len(hops)
    pops = []
    for a, b in pairs:
        d = dist[a]; db = d[b]
        below = sum(1 for x in d.values() if x < db)
        same = sum(1 for x in d.values() if x == db)
        pops.append(below + (same + 1) / 2)
    deg = [len(adj[i]) for i in range(n)]
    far = sum(1 for l in links if abs(l["u"] // 8 - l["v"] // 8) + abs(l["u"] % 8 - l["v"] % 8) > 1)
    return st.mean(hops), direct, st.mean(pops), min(deg), max(deg), far, len(links)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("items", nargs="+", help="rotulo:config.json")
    ap.add_argument("--patterns", nargs="+", default=["bit_reversal", "butterfly", "uniform"])
    a = ap.parse_args()
    for pat in a.patterns:
        print(f"\n== {pat} ==")
        print(f"{'topologia':<34}{'saltos':>7}{'diretos%':>9}{'nos ate dst':>12}{'grau':>7}{'longos':>8}{'links':>7}")
        for it in a.items:
            lab, p = it.split(":", 1)
            h, d, pops, dmin, dmax, far, m = analyze(load(p), pat)
            print(f"{lab:<34}{h:>7.2f}{100*d:>9.1f}{pops:>12.1f}{dmin:>4}-{dmax:<2}{far:>8}{m:>7}")
    print("\n'nos ate dst' = nos extraidos pelo Dijkstra (aprox.) antes de chegar ao destino.")

if __name__ == "__main__":
    main()