#include "Stats.h"

// Inicialização única (alocação de memória real)
int Stats::entregues = 0;
int Stats::gerados = 0;
sc_time Stats::latencia_total = SC_ZERO_TIME;

void Stats::add_entrega(sc_time latencia) {
    entregues++;
    latencia_total += latencia;
}

void Stats::add_gerado(){
    gerados++;
}

double Stats::calcular_eficiencia(){
    if(gerados == 0) return 0.0;
    return ((double)entregues/ (double)gerados)*100.0;
}