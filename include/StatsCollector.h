#ifndef STATS_COLLECTOR_H
#define STATS_COLLECTOR_H

#include <systemc.h>
#include <map>
#include <vector>
#include <fstream>
#include <iostream>

struct FlowLog {
    sc_time start_time = SC_ZERO_TIME;
    sc_time setup_time = SC_ZERO_TIME;
    sc_time end_time = SC_ZERO_TIME;

    bool setup_done = false;
    bool end_done = false;
};

class StatsCollector {
private:
    std::map<int, FlowLog> logs;
    sc_mutex log_mutex;

public:
    void record_request(int flow_id, sc_time t){
        log_mutex.lock();
        logs[flow_id].start_time = t;
        log_mutex.unlock();
    }

    void record_setup(int flow_id, sc_time t){
        log_mutex.lock();
        logs[flow_id].setup_time = t;
        logs[flow_id].setup_done = true;
        log_mutex.unlock();
    }

    void record_finish(int flow_id, sc_time t){
        log_mutex.lock();
        logs[flow_id].end_time = t;
        logs[flow_id].end_done = true;
        log_mutex.unlock();
    }

    void generate_report(const std::string& filename) {
        if (logs.empty()) return;

        std::ofstream file(filename);
        file << "flow_id,control_latency_ns,data_latency_ns,total_latency_ns\n";

        double total_sum = 0;
        int completed_flows = 0;
        
        for (auto const& [id, log] : logs) {
            // AQUI ESTÁ O PULO DO GATO: Só processa se o fluxo terminou
            if (log.setup_done && log.end_done) {
                double control = (log.setup_time - log.start_time).to_double() / 1000.0;
                double data = (log.end_time - log.setup_time).to_double() / 1000.0;
                double total = control + data;
                
                file << id << "," << control << "," << data << "," << total << "\n";
                total_sum += total;
                completed_flows++;
            } else {
                file << id << ",INCOMPLETO,INCOMPLETO,INCOMPLETO\n";
            }
        }

        if (completed_flows > 0) {
            file << "\nAverage Total Latency: " << (total_sum / completed_flows) << " ns\n";
        } else {
            file << "\nAverage Total Latency: N/A (Nenhum fluxo finalizado)\n";
        }

        file.close();
    }
};

#endif // STATS_COLLECTOR_H