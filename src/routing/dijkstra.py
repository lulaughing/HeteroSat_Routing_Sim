# -*- coding: utf-8 -*-
"""
File: src/routing/dijkstra.py
Description: 基于 Dijkstra 的最短路径算法 (基准)
修正: 增加节点类型约束，禁止地面站作为中继节点
"""
import networkx as nx
from src.routing.strategy import RoutingStrategy

class DijkstraStrategy(RoutingStrategy):
    def __init__(self, weight_key='delay'):
        super().__init__()
        self.name = "Dijkstra"
        self.weight_key = weight_key

    def find_path(self, G, src, dst, qos_constraints=None):
        """
        标准 Dijkstra 寻路，但遵循物理约束 (No Ground Relay)
        """
        # 定义动态权重函数 (用于过滤非法节点)
        def weight_function(u, v, d):
            # =================================================
            # [物理约束]: 禁止地面站作为中继
            # =================================================
            # 获取目标节点 v 的类型
            try:
                node_type_v = G.nodes[v].get('type', 'Unknown')
            except KeyError:
                node_type_v = 'Unknown'

            # 规则: 如果下一跳 v 是地面站/设施，但不是最终目的地 dst
            # 则视为断路 (返回 None)
            if node_type_v in ['Ground', 'Facility'] and v != dst:
                return None
            
            # =================================================
            # [标准逻辑]: 返回链路权重 (通常是 delay)
            # =================================================
            return d.get(self.weight_key, 1)

        try:
            # 使用自定义权重函数的 Dijkstra
            path = nx.dijkstra_path(G, src, dst, weight=weight_function)
            
            # 计算路径指标 (仅用于记录)
            total_delay = 0
            total_dist = 0
            for i in range(len(path)-1):
                u, v = path[i], path[i+1]
                edge = G[u][v]
                total_delay += edge.get('delay', 0)
                total_dist += edge.get('distance', 0)
            
            return path, {'delay': total_delay, 'distance': total_dist}
            
        except nx.NetworkXNoPath:
            return None, {}
        except Exception as e:
            # print(f"Dijkstra Error: {e}")
            return None, {}