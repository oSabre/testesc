#!/usr/bin/env python3
"""
compare_final_eval.py -- regressao (Fase 0.5): compara dois final_eval_*.csv
(candidate,pattern,mean,std,completion,...). Com o binario novo e o parametro de
comprimento DESLIGADO, os resultados devem ser identicos aos de antes.

Uso:  py compare_final_eval.py final_eval_bfs_src_cu16.csv final_eval_bfs_wire_check.csv
Sai com codigo 0 se todas as linhas coincidem (|dif| <= --tol em mean e std) e a
conclusao e 100% nas duas; 1 caso contrario.
"""
import argparse, csv, sys

def load(p):
    return {(r["candidate"], r["pattern"]): r for r in csv.DictReader(open(p, newline=""))}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("antes"); ap.add_argument("depois")
    ap.add_argument("--tol", type=float, default=1e-9)
    a = ap.parse_args()
    A, B = load(a.antes), load(a.depois)
    only_a, only_b = sorted(set(A) - set(B)), sorted(set(B) - set(A))
    bad, worst = [], 0.0
    for k in sorted(set(A) & set(B)):
        dm = abs(float(A[k]["mean"]) - float(B[k]["mean"]))
        ds = abs(float(A[k]["std"]) - float(B[k]["std"]))
        worst = max(worst, dm, ds)
        comp_ok = float(A[k]["completion"]) == 100.0 and float(B[k]["completion"]) == 100.0
        if dm > a.tol or ds > a.tol or not comp_ok:
            bad.append((k, dm, ds, A[k]["completion"], B[k]["completion"]))
    print(f"linhas comparadas: {len(set(A) & set(B))} | so no antes: {len(only_a)} | so no depois: {len(only_b)}")
    print(f"maior diferenca absoluta em mean/std: {worst:.3g}")
    for k in only_a[:10]: print("  so no antes :", k)
    for k in only_b[:10]: print("  so no depois:", k)
    for k, dm, ds, ca, cb in bad[:20]:
        print(f"  DIFERE {k}: dmean={dm:.4g} dstd={ds:.4g} conclusao {ca} -> {cb}")
    ok = not bad and not only_a and not only_b
    print("RESULTADO:", "IDENTICO (regressao OK)" if ok else "DIFERENTE (investigar)")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()