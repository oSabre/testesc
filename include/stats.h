#ifndef STATS_H
#define STATS_H
#include <systemc.h>

class Stats {
public:
    static int entregues;
    static int gerados;
    static sc_time latencia_total;
    
    static void add_entrega(sc_time latencia);
    static void add_gerado();
    static double calcular_eficiencia();
};

#endif