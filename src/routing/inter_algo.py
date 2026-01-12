# -*- coding: utf-8 -*-
"""
File: src/routing/inter_algo.py
Description: 域间路由算法 (GEO层)
对应论文: 4.3.2 节 (基于多约束剪枝 + 拥塞感知加权的 Dijkstra)
"""
import networkx as nx
import math
from src.routing.strategy import RoutingStrategy

class InterDomainAlgorithm(RoutingStrategy):
    def __init__(self):
        super().__init__()
        self.name = "InterDomain_Smart_Dijkstra"
        
        # 归一化因子 (论文参数)
        self.D_MAX = 2000.0  # 虚拟链路最大时延估值
        self.L_MAX = 0.1     # 虚拟链路最大丢包率估值
        self.LAMBDA = 1.0    # 拥塞惩罚系数
        self.GAMMA = 8.0     # 拥塞敏感度 (陡峭程度)

    def _get_qos_weights(self, service_type):
        """
        根据业务类型动态调整权重 (对应论文 4.2.2)
        """
        # 1. 时延敏感型 -> 增大 Alpha
        if service_type in ['Video_Live', 'Voice_VoIP', 'Telemetry_Control']:
            return 0.8, 0.2 # alpha, beta
            
        # 2. 可靠性/吞吐量敏感型 -> 增大 Beta
        elif service_type == 'Remote_Sensing':
            return 0.2, 0.8
            
        # 3. 默认平衡
        return 0.5, 0.5

    def find_path(self, G_vir, src_vir, dst_vir, qos_constraints=None):
        """
        在虚拟拓扑上计算宏观路径
        :param qos_constraints: {'bandwidth': 50, 'service_type': 'Remote_Sensing', ...}
        """
        # 0. 基础校验
        if src_vir not in G_vir or dst_vir not in G_vir:
            return None, {}

        # 获取约束参数
        req_bw = qos_constraints.get('bandwidth', 0) if qos_constraints else 0
        service_type = qos_constraints.get('service_type', 'Unknown') if qos_constraints else 'Unknown'
        
        # 获取动态权重 alpha (时延), beta (丢包)
        alpha, beta = self._get_qos_weights(service_type)

        # 定义动态权重函数 (NetworkX 支持传入函数作为 weight)
        def weight_function(u, v, d):
            # --- 步骤 1: 拓扑剪枝 (Pruning) ---
            # 获取虚拟边聚合后的容量与负载
            capacity = d.get('capacity', 1e-5)
            used = d.get('used_bw', 0)
            remaining = capacity - used
            
            # 如果剩余带宽不足，返回 None (视为断开)
            if remaining < req_bw:
                return None
            
            # --- 步骤 2: 拥塞感知权值计算 (Weighting) ---
            # 获取虚拟边聚合指标
            delay = d.get('delay', 10)
            loss = d.get('loss', 0.001)
            
            # 计算负载率 rho
            rho = used / capacity if capacity > 0 else 1.0
            if rho > 1.0: rho = 1.0
            
            # 代入论文公式: 
            # W = (alpha * norm_D + beta * norm_L) * (1 + lambda * exp(gamma * rho))
            base_cost = (alpha * (delay / self.D_MAX)) + (beta * (loss / self.L_MAX))
            congestion_penalty = 1.0 + self.LAMBDA * math.exp(self.GAMMA * rho)
            
            return base_cost * congestion_penalty

        # --- 步骤 3: 最短路径搜索 ---
        try:
            # 使用自定义权重函数运行 Dijkstra
            path = nx.dijkstra_path(G_vir, src_vir, dst_vir, weight=weight_function)
            
            # 计算路径预估指标 (用于日志)
            total_est_delay = 0
            for i in range(len(path)-1):
                total_est_delay += G_vir[path[i]][path[i+1]].get('delay', 0)
                
            return path, {'est_delay': total_est_delay}
            
        except nx.NetworkXNoPath:
            return None, {}
        except Exception as e:
            # print(f"InterDomain Algo Error: {e}")
            return None, {}