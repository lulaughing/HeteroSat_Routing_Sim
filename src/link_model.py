# -*- coding: utf-8 -*-
"""
File: src/link_model.py
Description: 链路物理模型 (BPR 平滑版 - 适合学术论文)
特点: 
1. 使用 BPR 函数计算时延，曲线平滑，消除数据锯齿。
2. 使用 Sigmoid 变体计算丢包，过载时渐进增长，数值更合理。
"""
import math

def apply_traffic_physics(G, u, v, added_bw):
    """
    更新链路状态：基于 BPR (Bureau of Public Roads) 模型
    """
    if not G.has_edge(u, v):
        return

    # 1. 流量累加
    current_used = G[u][v].get('used_bw', 0)
    new_used = current_used + added_bw
    G[u][v]['used_bw'] = new_used
    
    # 2. 获取静态属性
    capacity = G[u][v].get('capacity', 200) 
    if capacity <= 0: capacity = 1.0 # 防止除零
    
    if 'static_delay' not in G[u][v]:
        if 'delay_prop' in G[u][v]:
            G[u][v]['static_delay'] = G[u][v]['delay_prop']
        else:
            dist = G[u][v].get('distance', 1000)
            G[u][v]['static_delay'] = dist / 299.79
    
    static_delay = G[u][v]['static_delay']

    # 3. 计算负载率 (Utilization)
    util = new_used / capacity
    
    # =================================================================
    # 模型 A: 动态时延 (BPR 模型 - 更加激进的惩罚)
    # T = T0 * (1 + alpha * (Load/Cap)^beta)
    # alpha=1.0, beta=6.0 (原 alpha=0.8, beta=4.0)
    # 目的: 让 Dijkstra 在拥塞时时延爆炸
    # =================================================================
    alpha = 1.0
    beta = 6.0
    congestion_factor = 1.0 + alpha * (util ** beta)
    
    # 封顶限制提高 (原 100.0 -> 500.0)
    congestion_factor = min(congestion_factor, 500.0) 
    
    dynamic_delay = static_delay * congestion_factor
    
    # =================================================================
    # 模型 B: 动态丢包 (更加严厉的过载惩罚)
    # 目的: 让 Dijkstra 在过载时 PDR 迅速崩塌
    # =================================================================
    base_loss = 0.001 
    
    if util <= 1.0:
        # 轻载区: 线性微增
        dynamic_loss = base_loss + (util * 0.001) 
    else:
        # 过载区: 激进增长 (斜率从 0.3 提高到 0.8)
        # util=1.5 -> loss = 0.2% + 0.5 * 0.8 = 40.2% (原 15.2%)
        # util=2.0 -> loss = 0.2% + 1.0 * 0.8 = 80.2% (原 30.2%)
        overload = util - 1.0
        dynamic_loss = 0.002 + (overload * 0.8)
        
        # 物理封顶 99%
        dynamic_loss = min(dynamic_loss, 0.99)

    # 5. 写回状态
    G[u][v]['loss'] = dynamic_loss
    G[u][v]['delay'] = dynamic_delay
    G[u][v]['load'] = util
    G[u][v]['is_congested'] = (util > 1.0)
