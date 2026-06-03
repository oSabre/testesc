#include <systemc.h>
#include "TestBurst.h"

int sc_main(int argc, char* argv[]) {
    TestBurst test("Burst_Bateria_1");
    sc_start();
    return 0;
}

//O que faz: Submete o roteador a uma rajada contínua de 50 flits, testando o processamento em ritmo de pipeline (latência de 2 ciclos).
//Por que é importante: Valida o Throughput (Vazão) do hardware.
// Garante que, sob carga, o roteador não apresenta erros de sincronização (como pulo de IDs) 
// e que o pipeline interno consegue manter a ordem de chegada (FIFO).

//O que esperar: O log deve exibir uma sequência ininterrupta de IDs de 1 a 50, 
//com um espaçamento temporal constante entre cada recebimento, comprovando que o roteador sustenta carga máxima sem desincronizar.