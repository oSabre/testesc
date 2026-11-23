# Configuracao do gem5 (v23.0.0.1, RISC-V, modo SE) para o kernel de roteamento.
# Tipo de core: variavel de ambiente CPU = MINOR (padrao) | TIMING | O3   (ATOMIC nao tem temporizacao)
# Uso: gem5.opt --outdir=DIR run.py ./kernel_rv topo.txt saida.csv K semente busy_pct
import os, sys
from gem5.components.boards.simple_board import SimpleBoard
from gem5.components.cachehierarchies.classic.private_l1_cache_hierarchy import PrivateL1CacheHierarchy
from gem5.components.memory.single_channel import SingleChannelDDR3_1600
from gem5.components.processors.simple_processor import SimpleProcessor
from gem5.components.processors.cpu_types import CPUTypes
from gem5.isas import ISA
from gem5.resources.resource import CustomResource
from gem5.simulate.simulator import Simulator

cache = PrivateL1CacheHierarchy(l1d_size="32KiB", l1i_size="32KiB")
mem = SingleChannelDDR3_1600(size="512MiB")
CPU = os.environ.get("CPU", "MINOR").upper()
cpu = SimpleProcessor(cpu_type=getattr(CPUTypes, CPU), num_cores=1, isa=ISA.RISCV)
board = SimpleBoard(clk_freq="100MHz", processor=cpu, memory=mem, cache_hierarchy=cache)
board.set_se_binary_workload(CustomResource(sys.argv[1]), arguments=sys.argv[2:])
Simulator(board=board).run()