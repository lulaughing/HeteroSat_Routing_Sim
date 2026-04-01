# -*- coding: utf-8 -*-
"""
File: src/routing/dijkstra_qos.py
Description: 带 QoS 约束的 Dijkstra 算法 (CSPF)
核心逻辑: 
1. 带宽剪枝: 剩余带宽 < 需求 -> 断路
2. 节点类型约束: 禁止 Ground/Facility 节点作为中继 (只能是源或宿)
"""
import networkx as nx
import logging

class QoSDijkstraAlgorithm:
    def __init__(self, logger=None):
        self.name = "QoS-Dijkstra"
        self.logger = logger

    def find_path(self, G, src, dst, qos_requirements):
        """
        寻找满足 QoS (主要是带宽) 的最短路径
        同时实施节点类型约束，防止地面站透传
        """
        req_bw = qos_requirements.get('bandwidth', 0)
        pruned_bw_count = 0
        pruned_node_count = 0
        
        # 定义动态权重函数 (NetworkX Dijkstra 会调用此函数获取边权)
        def weight_function(u, v, d):
            nonlocal pruned_bw_count, pruned_node_count
            
            # =========================================================
            # [新增修复]: 禁止地面站作为中继 (Anti-Ground-Relay)
            # =========================================================
            # 获取目标节点 v 的类型
            # 注意: 我们利用闭包访问外层的 G
            try:
                node_type_v = G.nodes[v].get('type', 'Unknown')
            except KeyError:
                node_type_v = 'Unknown'

            # 规则: 如果 v 是地面站/设施，且 v 不是本次路由的终点 dst
            # 那么禁止从 u 流向 v。
            # 逻辑: 只有当 v 是目的地时，才允许数据流入地面站。
            if node_type_v in ['Ground', 'Facility'] and v != dst:
                # 这是一个非法的中继尝试 (如 Sat -> Ground -> Sat)
                pruned_node_count += 1
                return None 

            # =========================================================
            # [原有逻辑]: 带宽剪枝 (Bandwidth Pruning)
            # =========================================================
            # 1. 获取链路容量和已用带宽
            capacity = d.get('capacity', 0)
            used = d.get('used_bw', 0)
            remaining = capacity - used
            
            # 2. 如果剩余带宽 < 需求，则此路不通
            if remaining < req_bw:
                pruned_bw_count += 1
                return None # NetworkX 会忽略返回 None 的边
            
            # 3. 如果满足上述条件，返回时延作为代价 (Cost)
            return d.get('delay', 1)

        # --- 日志记录 ---
        if self.logger:
            self.logger.info(f"[{self.name}] Finding path {src} -> {dst} (Req BW: {req_bw}M)")

        # --- 执行算法 ---
        try:
            # 使用 NetworkX 的标准 Dijkstra，但注入了带剪枝逻辑的权重函数
            path = nx.dijkstra_path(G, src, dst, weight=weight_function)
            
            if self.logger:
                self.logger.info(f"[{self.name}] Success. Hops: {len(path)-1}. "
                                 f"Pruned: {pruned_bw_count} (BW), {pruned_node_count} (Node).")
            
            return path, True
            
        except nx.NetworkXNoPath:
            if self.logger:
                self.logger.warning(f"[{self.name}] No path found. "
                                    f"Pruned: {pruned_bw_count} (BW), {pruned_node_count} (Node).")
            return [], False
            
        except Exception as e:
            if self.logger:
                self.logger.error(f"[{self.name}] Error: {e}")
            return [], False
