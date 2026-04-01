# -*- coding: utf-8 -*-
"""
File: src/routing/iga/iga_mutation.py
Description: 变异操作 (严格遵循 Thesis 4.4.5 - 拥塞感知自适应变异)
"""
import networkx as nx
import random
import math
from src.routing.iga.iga_fitness import evaluate_path
from src.utils import get_algo_logger, get_lazy_logger

alog = get_lazy_logger(get_algo_logger)

# [论文参数]
P_BASE = 0.05      # 基准变异率
P_MAX = 0.8        # 最大变异率
RHO_TH = 0.7       # 拥塞阈值 (负载超过70%开始显著增加变异概率)
GAMMA_MUT = 10.0   # 敏感度系数

def mutation(G, path):
    """
    拥塞感知变异：
    1. 计算自适应变异概率 P_mut (基于路径最大负载)
    2. 如果触发，执行"感知-切除-修复"逻辑
    """
    if len(path) < 3: return path
    
    # --- 1. 计算自适应变异概率 (Thesis 4-17) ---
    # 获取路径的最大负载率 rho_max
    m = evaluate_path(G, path)
    rho_max = m['max_util']
    
    # Sigmoid 自适应公式
    try:
        sigmoid_part = 1.0 / (1.0 + math.exp(-GAMMA_MUT * (rho_max - RHO_TH)))
        p_mut = P_BASE + (P_MAX - P_BASE) * sigmoid_part
    except OverflowError:
        p_mut = P_MAX
        
    # 随机决定是否变异
    if random.random() > p_mut:
        return path # 不变异
        
    # --- 2. 执行拥塞规避操作 (Thesis 4.4.5 Step 1-4) ---
    try:
        # Step 1: 定位热点链路 l_hot (u, v)
        # 找到路径中利用率最高的那一段
        max_u_val = -1
        hot_idx = -1
        
        for i in range(len(path)-1):
            u, v = path[i], path[i+1]
            if G.has_edge(u, v):
                util = G[u][v].get('used_bw', 0) / G[u][v].get('capacity', 1)
                if util > max_u_val:
                    max_u_val = util
                    hot_idx = i
        
        if hot_idx == -1: return path
        
        # 确定局部重构的锚点 (回溯m跳，延伸n跳，这里取1)
        # 即切除 hot_idx 及其前后节点
        start_idx = max(0, hot_idx - 1)
        end_idx = min(len(path)-1, hot_idx + 2)
        
        v_start = path[start_idx]
        v_end = path[end_idx]
        
        if v_start == v_end: return path
        
        # Step 2: 构建局部虚拟拓扑 G_temp (移除热点链路)
        # 实际上我们不需要复制整个图，只需要在寻路时避开该边即可
        # 或者暂时将该边的权重设为无穷大
        
        hot_u, hot_v = path[hot_idx], path[hot_idx+1]
        
        # 保存原权重
        orig_weight = G[hot_u][hot_v].get('delay', 10)
        # 临时将热点链路阻断 (逻辑切除)
        G[hot_u][hot_v]['delay'] = float('inf')
        
        try:
            # Step 3: 搜索旁路 (轻量级代价)
            # 论文建议用线性代价: Cost = 1/B_res + w*D
            # 这里简化为 Dijkstra (weight='delay')，因为已经把堵的路设为 inf 了
            sub_path = nx.shortest_path(G, v_start, v_end, weight='delay')
            
            # Step 4: 拼接新路径
            # 原路径: [... v_start, ... old_seg ..., v_end ...]
            # 新路径: [... v_start] + sub_path[1:-1] + [v_end ...]
            new_path = path[:start_idx] + sub_path + path[end_idx+1:]
            
            # 恢复权重
            G[hot_u][hot_v]['delay'] = orig_weight
            
            alog.debug(f"      [Mut] 拥塞规避: 移除 {hot_u}-{hot_v} (Util={max_u_val:.2f}), 找到旁路")
            return new_path
            
        except nx.NetworkXNoPath:
            # 找不到旁路，恢复权重并返回原路径
            G[hot_u][hot_v]['delay'] = orig_weight
            return path
            
    except Exception as e:
        return path

    return path
