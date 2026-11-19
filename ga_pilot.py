#!/usr/bin/env python3
"""
ga_pilot.py -- piloto de saturacao do plano de controle.
Varre num_control_units x duration_us (x padroes) para topologias de
referencia (mesh, small-world, opcionalmente aleatorias) e mostra, para cada
combinacao: taxa de conclusao, latencia dos concluidos (exata) e latencia
penalizada. Objetivo: achar o regime em que a taxa de conclusao e ~100% e,
portanto, a latencia mede a rede e nao a saturacao.

Uso:
  py ga_pilot.py --bin ./main.exe --cus-list 2 4 8 16 --durations 15 50 100 200 \
     --refs mesh:configs/configs_ciclos/config_mesh_64.json \
            smallworld:configs/configs_ciclos/config_irregular_smallworld_64.json \
     --patterns uniform bit_reversal butterfly --replicas 3
Saida: pilot.csv + tabela. Marca com [OK] as combinacoes com conclusao >= --target (95%)
em TODAS as referencias.
"""
import argparse, copy, csv
from concurrent.futures import ThreadPoolExecutor
import ga_common as gc
gc._ca.disable()  # o piloto explora de proposito regimes com conclusao < 100%


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    gc.common_args(ap)
    ap.add_argument("--cus-list", type=int, nargs="+", default=[2, 4, 8, 16])
    ap.add_argument("--durations", type=float, nargs="+", default=[15, 50, 100, 200])
    ap.add_argument("--patterns", nargs="+", default=["uniform", "bit_reversal", "butterfly"])
    ap.add_argument("--refs", nargs="+", required=True, help="rotulo:config.json")
    ap.add_argument("--spacings", type=int, nargs="+", default=[100],
                    help="spacing_ns entre fluxos (carga): 100=padrao; 400 => 4x menos carga")
    ap.add_argument("--replicas", type=int, default=3)
    ap.add_argument("--seed-start", type=int, default=500)
    ap.add_argument("--target", type=float, default=95.0)
    ap.add_argument("--out", default="pilot.csv")
    a = ap.parse_args()
    refs = {}
    for it in a.refs:
        k, p = it.split(":", 1)
        refs[k] = gc.edges_from_config(p)
    seeds = list(range(a.seed_start, a.seed_start + a.replicas))
    jobs = [(p, c, d, k, sp) for p in a.patterns for c in a.cus_list for d in a.durations for sp in a.spacings for k in refs]
    def run(j):
        p, c, d, k, sp = j
        la = copy.copy(a)            # copia por job: evita corrida entre threads
        la.traffic, la.cus, la.duration_us, la.spacing_ns = p, c, d, sp
        ev = gc.evaluator_from_args(la, seeds)
        r = ev.evaluate(refs[k])
        return j, r
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        res = list(ex.map(run, jobs))
    rows = [{"pattern": p, "cus": c, "duration_us": d, "spacing_ns": sp, "topology": k,
             "completion": r["completion"], "lat_completed": r.get("exact"),
             "control_lat": r.get("control"), "data_lat": r.get("data"),
             "fitness": r["fitness"]} for (p, c, d, k, sp), r in res]
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(f"{'padrao':<13}{'CUs':>4}{'dur':>5}{'esp':>5}  " + "  ".join(f"{k[:9]:>9}: concl% ctrl data" for k in refs) + "  ok")
    for p in a.patterns:
        for c in a.cus_list:
            for d in a.durations:
                for sp in a.spacings:
                    sel = {r["topology"]: r for r in rows if (r["pattern"], r["cus"], r["duration_us"], r["spacing_ns"]) == (p, c, d, sp)}
                    ok = all(r["completion"] >= a.target for r in sel.values())
                    f = lambda x: f"{x:>7.1f}" if x is not None else "    N/A"
                    cells = "  ".join(f"{sel[k]['completion']:>9.1f}   {f(sel[k]['control_lat'])} {f(sel[k]['data_lat'])}" for k in refs)
                    print(f"{p:<13}{c:>4}{d:>5.0f}{sp:>5}  {cells} {'[OK]' if ok else ''}")
    print(f"\nEscolha a menor combinacao [OK] (CUs realistas, ate 16) em TODOS os padroes; "
          f"use-a como --cus/--duration-us no GA. Resultado completo: {a.out}")

if __name__ == "__main__":
    main()