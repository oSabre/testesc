#ifndef ROUTING_STRATEGY_H
#define ROUTING_STRATEGY_H

#include <vector>
#include "TopologyManager.h"

class RoutingStrategy {
public:
    virtual ~RoutingStrategy() {}
    virtual std::vector<int> calculate_route(int src, int dst, const TopologyManager& tm) = 0;
};

#endif