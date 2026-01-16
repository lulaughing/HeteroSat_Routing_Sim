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
        self.weight_key = weight_key  # <--- 1. 这里接收并存储了 'static_delay'
        # print("标准 Dijkstra 寻路，但遵循物理约束 (No Ground Relay)")

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
            # 则视为断路 (返回无穷大)
            if node_type_v in ['Ground', 'Facility'] and v != dst:
                return float('inf')
            
            # =================================================
            # [标准逻辑]: 返回链路权重
            # =================================================
            w = d.get(self.weight_key, 1) # <--- 2. 这里读取了 d['static_delay']
            # print(f"[Dijkstra CHECK] self.weight_key = ", self.weight_key)

            # =================================================
            # [DEBUG] 验证 static_delay 是否生效
            # =================================================
            # 只有当正在使用 static_delay 时，才进行抽样打印
            # 这里的逻辑是：只在第一次调用时打印一次，避免刷屏
            if self.weight_key == 'static_delay' and not hasattr(self, '_logged_once'):
                # print(f"\n[Dijkstra CHECK] Mode={self.weight_key}, Sample Weight({u}->{v})={w}")
                # 如果 w > 100 (通常 static_delay 很小，约 5-50ms)，说明可能读错了
                if w > 100:
                    print(f"⚠️ 警告：检测到异常大的静态时延 ({w})，请检查 topology.py 初始化！")
                self._logged_once = True
            
            return w

        try:
            # 使用自定义权重函数的 Dijkstra
            path = nx.dijkstra_path(G, src, dst, weight=weight_function)
            
            # 计算路径指标 (仅用于记录，这里依然统计的是当前实际的 delay，用于评估)
            total_delay = 0
            total_dist = 0
            for i in range(len(path)-1):
                u, v = path[i], path[i+1]
                edge = G[u][v]
                total_delay += edge.get('delay', 0)     # 注意：结果统计仍用动态时延（评估真实性能）
                total_dist += edge.get('distance', 0)
            
            return path, {'delay': total_delay, 'distance': total_dist}
            
        except nx.NetworkXNoPath:
            return None, {}
        except Exception as e:
            # print(f"Dijkstra Error: {e}")
            return None, {}