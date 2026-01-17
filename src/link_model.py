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
        dist = G[u][v].get('distance', 1000)
        G[u][v]['static_delay'] = dist / 299.79
    
    static_delay = G[u][v]['static_delay']

    # 3. 计算负载率 (Utilization)
    util = new_used / capacity
    
    # =================================================================
    # 模型 A: 动态时延 (BPR 模型 - 经典学术模型)
    # T = T0 * (1 + alpha * (Load/Cap)^beta)
    # alpha=0.8, beta=4.0 是针对排队网络的经验参数
    # 特点: util<1.0 时增长缓慢; util>1.0 时呈四次方增长，既平滑又有惩罚力
    # =================================================================
    alpha = 0.8
    beta = 4.0
    congestion_factor = 1.0 + alpha * (util ** beta)
    
    # 封顶限制 (防止数学爆炸，比如 util=10 时)
    congestion_factor = min(congestion_factor, 100.0) 
    
    dynamic_delay = static_delay * congestion_factor
    
    # =================================================================
    # 模型 B: 动态丢包 (平滑渐进模型)
    # 目标: util=1.0 -> Loss=0.1% (几乎无损)
    #       util=1.2 -> Loss=5%   (轻微拥塞)
    #       util=1.5 -> Loss=15%  (严重拥塞)
    #       util=2.0 -> Loss=30%  (不可用)
    # =================================================================
    base_loss = 0.001 # 0.1% 基础误码
    
    if util <= 1.0:
        # 轻载区: 线性微增
        dynamic_loss = base_loss + (util * 0.001) 
    else:
        # 过载区: 线性增长 (斜率 0.3)，比之前的指数爆炸温和得多
        # Loss = 0.2% + (util-1.0) * 0.3
        # ex: util=1.5 -> loss = 0.002 + 0.15 = 15.2%
        overload = util - 1.0
        dynamic_loss = 0.002 + (overload * 0.3)
        
        # 物理封顶 90%
        dynamic_loss = min(dynamic_loss, 0.90)

    # 5. 写回状态
    G[u][v]['loss'] = dynamic_loss
    G[u][v]['delay'] = dynamic_delay
    G[u][v]['is_congested'] = (util > 1.0)