#!/usr/bin/env python3
"""
migrate_config_to_cycles.py

Migra arquivos de config.json do formato antigo (latencias em nanosegundos
crus, alguns nem multiplos do periodo de clock) para o formato novo
(tudo em ciclos de clock inteiros, de verdade).

NAO mexe no campo "topology" (a estrutura da rede/links continua igual) --
so re-escreve o bloco "network_params".

MAPEAMENTO:
  link_transit_latency_ns   -> link_transit_latency_cycles  (ns / 10)
  retry_wait_ns             -> retry_wait_cycles             (ns / 10)
  retry_jitter_ns           -> retry_jitter_cycles           (ns / 10)
  control_plane_latency_ns  -> control_plane_latency_cycles  (ns / 10)
  dijkstra_base_ns_per_node \
  dijkstra_pq_op_ns          > REMOVIDOS -- a formula do custo do Dijkstra
  dijkstra_edge_check_ns    /  mudou de verdade (nao e so conversao de
                               unidade), entao esses 3 coeficientes antigos
                               nao tem um equivalente numerico direto. Sao
                               substituidos pelos defaults novos (1 ciclo
                               cada): dijkstra_dispatch_cycles,
                               dijkstra_init_cycles_per_node,
                               dijkstra_pq_op_cycles,
                               dijkstra_edge_check_cycles.
  (novo, sem equivalente antigo) arbitro_latency_cycles = 1

Se algum valor em ns NAO for multiplo exato de 10 (CLOCK_PERIOD), o script
AVISA e arredonda para o ciclo mais proximo -- isso muda o comportamento
calibrado daquele arquivo especifico, entao vale conferir os avisos.

USO:
    python3 migrate_config_to_cycles.py config.json
    python3 migrate_config_to_cycles.py "config_*.json"   (glob, varios arquivos)
    python3 migrate_config_to_cycles.py "config_*.json" --dry-run   (so mostra, nao escreve)
"""

import glob
import json
import math
import sys

CLOCK_PERIOD_NS = 10


def round_half_up(x):
    """Arredondamento 'tradicional' (0.5 sempre sobe), diferente do
    round() nativo do Python (que arredonda 0.5 para o PAR mais proximo --
    round(0.5)==0! Isso faria, por exemplo, control_plane_latency_ns=5
    virar 0 ciclos em vez de 1, mudando silenciosamente um atraso real
    para 'instantaneo'. round_half_up(0.5) == 1, como esperado)."""
    return math.floor(x + 0.5)

# (campo_antigo, campo_novo, obrigatorio)
NS_TO_CYCLES_FIELDS = [
    ("link_transit_latency_ns", "link_transit_latency_cycles"),
    ("retry_wait_ns", "retry_wait_cycles"),
    ("retry_jitter_ns", "retry_jitter_cycles"),
    ("control_plane_latency_ns", "control_plane_latency_cycles"),
]

OLD_DIJKSTRA_FIELDS = [
    "dijkstra_base_ns_per_node",
    "dijkstra_pq_op_ns",
    "dijkstra_edge_check_ns",
]

NEW_DIJKSTRA_DEFAULTS = {
    "dijkstra_dispatch_cycles": 1,
    "dijkstra_init_cycles_per_node": 1,
    "dijkstra_pq_op_cycles": 1,
    "dijkstra_edge_check_cycles": 1,
}

NEW_FIELD_DEFAULTS = {
    "arbitro_latency_cycles": 1,
}


def migrate_network_params(params, label):
    changed = False
    warnings = []

    for old_key, new_key in NS_TO_CYCLES_FIELDS:
        if old_key in params:
            ns_value = params.pop(old_key)
            cycles = ns_value / CLOCK_PERIOD_NS
            cycles_rounded = round_half_up(cycles)
            if abs(cycles - cycles_rounded) > 1e-9:
                warnings.append(
                    f"  [AVISO] {old_key}={ns_value} nao e multiplo exato de "
                    f"{CLOCK_PERIOD_NS}ns -- arredondado para {cycles_rounded} "
                    f"ciclo(s) ({cycles_rounded * CLOCK_PERIOD_NS}ns)."
                )
            params[new_key] = cycles_rounded
            changed = True
        elif new_key not in params:
            # nem o campo antigo nem o novo existem -- deixa para o
            # default do proprio C++ (main.cpp) assumir, nao force nada
            pass

    old_dijkstra_present = any(f in params for f in OLD_DIJKSTRA_FIELDS)
    if old_dijkstra_present:
        for f in OLD_DIJKSTRA_FIELDS:
            params.pop(f, None)
        for new_key, default in NEW_DIJKSTRA_DEFAULTS.items():
            params[new_key] = default
        warnings.append(
            "  [AVISO] coeficientes antigos do Dijkstra (ns, fracionarios) "
            "removidos -- a formula mudou de verdade (minimo 1 ciclo por "
            "operacao), nao e so conversao de unidade. Usando defaults "
            "novos (1 ciclo cada): " + ", ".join(NEW_DIJKSTRA_DEFAULTS.keys())
        )
        changed = True

    for new_key, default in NEW_FIELD_DEFAULTS.items():
        if new_key not in params:
            params[new_key] = default
            changed = True

    print(f"=== {label} ===")
    if warnings:
        for w in warnings:
            print(w)
    if changed:
        print("  Migrado.")
    else:
        print("  Nada para migrar (ja estava no formato novo, ou sem os campos antigos).")
    print()

    return changed


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv
    pattern = [a for a in sys.argv[1:] if a != "--dry-run"][0]

    paths = sorted(glob.glob(pattern))
    if not paths:
        print(f"Nenhum arquivo encontrado para o padrao: {pattern}")
        sys.exit(1)

    total_changed = 0
    for path in paths:
        with open(path) as f:
            cfg = json.load(f)

        if "network_params" not in cfg:
            print(f"=== {path} ===\n  [AVISO] sem 'network_params', pulando.\n")
            continue

        changed = migrate_network_params(cfg["network_params"], path)

        if changed and not dry_run:
            with open(path, "w") as f:
                json.dump(cfg, f, indent=2)
        if changed:
            total_changed += 1

    print(f"--- {total_changed}/{len(paths)} arquivo(s) migrado(s)"
          f"{' (dry-run, nada escrito)' if dry_run else ''} ---")


if __name__ == "__main__":
    main()