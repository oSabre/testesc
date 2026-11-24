#!/usr/bin/env python3
"""
area_model.py -- modelo de area (referencial TEORICO, mm2 a 28 nm) da Fase 2/3.

A_total = n_CU * A_core + A_NoC
A_NoC   = soma_nos A_roteador(portas = grau + 1 (porta local), largura do flit)
          + soma_enlaces A_enlace (2 canais unidirecionais por enlace; desprezivel)

Fonte dos numeros (justificativas em claude/calibracao_cores_e_area.md):
  * Roteador e enlace: DSENT (ext/dsent do gem5), Bulk32LVT, 1 rede virtual, 1 canal
    virtual, 16 buffers/porta, 100 MHz, buffer DFFRAM; escalado por (28/32)^2 para 28 nm.
    O roteador do DSENT e de pacotes (alocador, VCs): e um teto conservador para o
    roteador de circuito do simulador. A largura do flit NAO existe no simulador:
    e parametro teorico (base 64 bits; sensibilidade 32 e 128).
  * Cores (28 nm, MEEK, DAC 2025): Minor ~ Rocket 0,092; O3 ~ SonicBOOM 2,811
    (L1 do BOOM pode estar incluida: razao 30,6x e estimativa);
    TimingSimple ~ 0,027 (ESTIMATIVA pela razao PicoRV32/Rocket em 130 nm).
O fio NAO entra na area de silicio (o teto de fio e restricao separada).
"""
SCALE_32_TO_28 = (28.0 / 32.0) ** 2

# area do roteador a 32 nm (mm2), saida do DSENT: [largura do flit][portas]
ROUTER_32NM = {
    32:  {2: 0.00546, 3: 0.00837, 4: 0.01145, 5: 0.01472},
    64:  {2: 0.01108, 3: 0.01726, 4: 0.02389, 5: 0.03102},
    128: {2: 0.02352, 3: 0.03770, 4: 0.05353, 5: 0.07105},
}
# area de um canal unidirecional de 1 bit a 32 nm (mm2): 0,0000496 mm2 / 64 bits
LINK_32NM_PER_BIT = 0.0000496 / 64.0

CORE_MM2 = {"minor": 0.092, "o3": 2.811, "timing": 0.027}


def router_mm2(ports, flit=64):
    if flit not in ROUTER_32NM:
        raise ValueError("flit deve ser 32, 64 ou 128")
    t = ROUTER_32NM[flit]
    if ports < 2:                       # grau 0 nao ocorre (topologia conexa)
        ports = 2
    if ports > 5:
        raise ValueError("portas > 5")
    return t[ports] * SCALE_32_TO_28


def noc_area(edges, n, flit=64):
    """Devolve (area_total_noc, area_roteadores, area_enlaces) em mm2."""
    deg = [0] * n
    for u, v in edges:
        deg[u] += 1
        deg[v] += 1
    ar = sum(router_mm2(d + 1, flit) for d in deg)
    al = len(edges) * 2 * flit * LINK_32NM_PER_BIT * SCALE_32_TO_28
    return ar + al, ar, al


def total_area(edges, n, n_cu, core, flit=64):
    a, _, _ = noc_area(edges, n, flit)
    return n_cu * CORE_MM2[core] + a


if __name__ == "__main__":
    import ga_common as gc
    e = gc.mesh_edges(8)
    for w in (32, 64, 128):
        a, ar, al = noc_area(e, 64, w)
        print(f"mesh 8x8 flit {w:>3}: NoC {a:.4f} mm2 (roteadores {ar:.4f}, enlaces {al:.4f})"
              f" | + 16 Minor = {a + 16 * CORE_MM2['minor']:.4f}")