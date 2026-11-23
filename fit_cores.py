#!/usr/bin/env python3
"""Ajuste final dos coeficientes de custo por tipo de core (Fase 0.8) a partir dos all_calls.csv.

  python3 fit_cores.py minor=results_minor/all_calls.csv timing=results_timing/all_calls.csv o3=results_o3/all_calls.csv

Formas (as mesmas do simulador apos o patch de custo):
  BFS      : dispatch + init*N + pq_op*ops + edge*arestas                        (pisos 1)
  Dijkstra : dispatch + init*N + base*ops + pq_op*sum(log2 tam. fila) + edge*arestas (pisos 1,1,0,1,1)
Saida: coeficientes inteiros, erro relativo medio, custo na mesh 8x8 (L=112, sem ocupados), razao em relacao
ao primeiro core listado (que vira a referencia r=1) e as linhas --np prontas para o ga_final_eval.py.
Requer numpy (scipy opcional).
"""
import csv, sys
import numpy as np

def nnls(A, b, lb):
    b2 = b - A @ lb
    try:
        from scipy.optimize import nnls as _n
        d, _ = _n(A, b2, maxiter=50000)
    except Exception:
        d = np.zeros(A.shape[1]); AtA = A.T @ A; Atb = A.T @ b2
        for _ in range(50000):
            for k in range(len(d)):
                if AtA[k, k] > 0: d[k] = max(0.0, d[k] + (Atb[k] - AtA[k] @ d) / AtA[k, k])
    return lb + d

def load(path):
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        for k in ('N', 'L', 'busy_pct', 'ops', 'edges', 'log2sum', 'cycles', 'pops', 'pushes'): r[k] = float(r[k])
    return rows

def fit(rows, algo):
    R = [r for r in rows if r['algo'] == algo]
    y = np.array([r['cycles'] for r in R])
    if algo == 'bfs':
        X = np.array([[1, r['N'], r['ops'], r['edges']] for r in R]); lb = np.array([1, 1, 1, 1.0])
    else:
        X = np.array([[1, r['N'], r['ops'], r['log2sum'], r['edges']] for r in R]); lb = np.array([1, 1, 0, 1, 1.0])
    c = nnls(X, y, lb); ci = np.round(c)
    mre = lambda cc: float(np.mean(np.abs(X @ cc - y) / y) * 100)
    ss = lambda cc: 1 - ((y - X @ cc) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    mesh = [r['cycles'] for r in R if r['N'] == 64 and r['L'] == 112 and r['busy_pct'] == 0]
    mm = [X[i] for i, r in enumerate(R) if r['N'] == 64 and r['L'] == 112 and r['busy_pct'] == 0]
    return dict(c=c, ci=ci, mre=mre(ci), mre_free=mre(c), r2=ss(ci), n=len(R),
                mesh_meas=float(np.mean(mesh)) if mesh else float('nan'),
                mesh_model=float(np.mean([x @ ci for x in mm])) if mm else float('nan'))

def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    cores = [a.split('=', 1) for a in sys.argv[1:]]
    res = {}
    for name, path in cores:
        rows = load(path)
        res[name] = {a: fit(rows, a) for a in ('bfs', 'dijkstra')}
        cyc = np.mean([r['cycles'] for r in rows]); ins = np.mean([r.get('insts', 0) for r in rows]) if 'insts' in rows[0] else 0
    ref = cores[0][0]
    print("== Coeficientes por core (ciclos do core; inteiros) ==")
    for name, _ in cores:
        b, d = res[name]['bfs'], res[name]['dijkstra']
        print(f"\n[{name}]  {b['n']} chamadas BFS / {d['n']} Dijkstra")
        print(f"  BFS      dispatch {b['ci'][0]:.0f}  init {b['ci'][1]:.0f}  pq_op {b['ci'][2]:.0f}  edge {b['ci'][3]:.0f}   erro rel. medio {b['mre']:.1f}% (livre {b['mre_free']:.1f}%), R2 {b['r2']:.4f}")
        print(f"           mesh 8x8: medido {b['mesh_meas']:.0f}, modelo {b['mesh_model']:.0f}")
        print(f"  Dijkstra dispatch {d['ci'][0]:.0f}  init {d['ci'][1]:.0f}  base {d['ci'][2]:.0f}  pq_op {d['ci'][3]:.0f}  edge {d['ci'][4]:.0f}   erro rel. medio {d['mre']:.1f}% (livre {d['mre_free']:.1f}%), R2 {d['r2']:.4f}")
        print(f"           mesh 8x8: medido {d['mesh_meas']:.0f}, modelo {d['mesh_model']:.0f}")
    print(f"\n== Velocidade relativa a '{ref}' (custo medido na mesh 8x8; r_equiv = custo_ref/custo_core) ==")
    for name, _ in cores:
        rb = res[ref]['bfs']['mesh_meas'] / res[name]['bfs']['mesh_meas']
        rd = res[ref]['dijkstra']['mesh_meas'] / res[name]['dijkstra']['mesh_meas']
        print(f"  {name:10s} BFS {res[name]['bfs']['mesh_meas']:8.0f} ciclos (r_equiv {rb:.2f})   Dijkstra {res[name]['dijkstra']['mesh_meas']:8.0f} (r_equiv {rd:.2f})")
    print("\n== Linhas --np para o ga_final_eval.py / run_cu_sweep.sh ==")
    for name, _ in cores:
        b, d = res[name]['bfs']['ci'], res[name]['dijkstra']['ci']
        print(f"  [{name}] BFS: --np routing_algorithm=bfs --np dijkstra_dispatch_cycles={b[0]:.0f} --np dijkstra_init_cycles_per_node={b[1]:.0f} --np dijkstra_pq_op_cycles={b[2]:.0f} --np dijkstra_edge_check_cycles={b[3]:.0f}")
        print(f"  [{name}] DIJ: --np routing_algorithm=dijkstra --np dijkstra_dispatch_cycles={d[0]:.0f} --np dijkstra_init_cycles_per_node={d[1]:.0f} --np dijkstra_pq_base_cycles={d[2]:.0f} --np dijkstra_pq_op_cycles={d[3]:.0f} --np dijkstra_edge_check_cycles={d[4]:.0f}")
    print("\nObs.: todos os cores rodam a 100 MHz no gem5 (r = 1 para cada um); a vantagem de um core mais rapido aparece nos\n"
          "coeficientes menores. S (ciclos) = custo na mesh 8x8; para run_cu_sweep.sh use S_US = ciclos*0,01 us.")

if __name__ == '__main__':
    main()