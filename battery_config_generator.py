#!/usr/bin/env python3
"""
battery_config_generator.py

Combina as 8 topologias base (mesh/fewlinks/morelinks/smallworld x 16/64
nos) com os 3 padroes de trafego (uniform, bit_reversal, butterfly),
gerando as 24 configuracoes da bateria completa de testes.

So o campo "traffic" muda entre as 3 variantes de cada topologia -- tudo
mais (network_params, simulation) fica identico ao arquivo base, para
manter a comparacao justa.

Uso: python3 battery_config_generator.py
(le os config_*.json base do diretorio atual, escreve os 24 arquivos
config_battery_*.json e o manifest battery_manifest.txt)
"""

import json

# rotulo -> arquivo de topologia base (deve existir no diretorio atual,
# gerado por topology_generator.py)
TOPOLOGIES = {
    "mesh_16":        "config_mesh.json",
    "smallworld_16":  "config_irregular_smallworld.json",
    "fewlinks_16":    "config_irregular_fewlinks_16.json",
    "morelinks_16":   "config_irregular_morelinks_16.json",
    "mesh_64":        "config_mesh_64.json",
    "smallworld_64":  "config_irregular_smallworld_64.json",
    "fewlinks_64":    "config_irregular_fewlinks_64.json",
    "morelinks_64":   "config_irregular_morelinks_64.json",
}

# rotulo -> como configurar o bloco "traffic" para cada padrao.
# num_packets identico entre padroes (mesmo volume total de trafego, para
# comparacao justa). uniform mantem o "seed" existente do arquivo base.
def traffic_block(pattern, base_traffic):
    num_packets = base_traffic.get("num_packets", 100)
    if pattern == "uniform":
        return {
            "mode": "uniform",
            "num_packets": num_packets,
            "source_file": base_traffic.get("source_file", "traces/trace_01.csv"),
            "seed": base_traffic.get("seed", 1),
        }
    elif pattern == "bit_reversal":
        return {"mode": "bit_reversal", "num_packets": num_packets}
    elif pattern == "butterfly":
        return {"mode": "butterfly", "num_packets": num_packets}
    else:
        raise ValueError(f"Padrao de trafego desconhecido: {pattern}")


def main():
    manifest_lines = []

    for topo_label, base_path in TOPOLOGIES.items():
        with open(base_path) as f:
            base_cfg = json.load(f)

        for pattern in ("uniform", "bit_reversal", "butterfly"):
            cfg = json.loads(json.dumps(base_cfg))  # copia profunda
            cfg["traffic"] = traffic_block(pattern, base_cfg.get("traffic", {}))

            out_name = f"config_battery_{topo_label}_{pattern}.json"
            with open(out_name, "w") as f:
                json.dump(cfg, f, indent=2)

            size = "16" if topo_label.endswith("_16") else "64"
            topo_family = topo_label.rsplit("_", 1)[0]
            manifest_lines.append(
                f"{out_name}\t{topo_family}\t{size}\t{pattern}"
            )
            print(f"  -> escrito: {out_name}")

    # newline="" evita que o Python (no Windows) traduza "\n" para "\r\n"
    # automaticamente -- sem isso, o "\r" sobrava grudado no ultimo campo
    # de cada linha quando o run_full_battery.sh (bash) le o arquivo, ja
    # que bash so reconhece "\n" como fim de linha.
    with open("battery_manifest.txt", "w", newline="") as f:
        f.write("config_file\ttopology\tsize\ttraffic\n")
        f.write("\n".join(manifest_lines) + "\n")

    print(f"\nManifest escrito: battery_manifest.txt ({len(manifest_lines)} combinacoes)")


if __name__ == "__main__":
    main()