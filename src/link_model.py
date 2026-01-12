# -*- coding: utf-8 -*-
"""
File: src/link_model.py
Description: 链路物理模型 (高敏感度/激进拥塞版)
"""
import math

def apply_traffic_physics(G, u, v, added_bw):
    """
    对图 G 中的边 (u, v) 施加流量，并根据激进的 M/M/1 模型更新物理属性
    """
    if not G.has_edge(u, v):
        return

    # 1. 累加流量
    current_used = G[u][v].get('used_bw', 0)
    new_used = current_used + added_bw
    G[u][v]['used_bw'] = new_used
    
    # 2. 获取物理静态属性
    # 注意: 这里的 capacity 默认值仅作备用，实际值由 topology.py 初始化时决定 (设为了 200)
    capacity = G[u][v].get('capacity', 200) 
    
    if 'static_delay' not in G[u][v]:
        dist = G[u][v].get('distance', 1000)
        G[u][v]['static_delay'] = dist / 299.79
    
    static_delay = G[u][v]['static_delay']

    # 3. 计算负载率 (Utilization)
    util = new_used / capacity if capacity > 0 else 1.0
    
    # 4. 动态丢包率 (Loss Model) - 激进版
    # 目的：让 Dijkstra 在严重拥塞时的 Loss 变得非常难看，体现物理世界的“丢包”
    if util <= 0.9:
        # 轻载：仅有微小的背景误码
        dynamic_loss = 0.001  
    elif util <= 1.0:
        # 预警区 (0.9~1.0): 丢包率线性上升到 5%，模拟路由器的主动队列管理 (RED)
        dynamic_loss = 0.001 + (util - 0.9) * 0.5 
    else:
        # 过载区 (>1.0): 严重拥塞，溢出即丢包
        # 增加 1.5 倍惩罚系数，让丢包率飙升得更快
        # 例如 util=2.0 时，Loss = 1 - 1/3 = 66%
        dynamic_loss = 1.0 - (1.0 / (util * 1.5))
        # 封顶 99% (物理上很难 100% 全丢，总有几个能挤过去)
        dynamic_loss = min(dynamic_loss, 0.99)
    
    # 5. 动态时延 (Delay Model) - M/M/1 激进版
    if util < 0.9:
        # 轻载区: 几乎无排队
        queue_factor = 1.0
    elif util < 1.0:
        # 重载区: 排队指数上升 (Standard M/M/1: 1 / (1-rho))
        queue_factor = 1.0 / (1.0 - util)
    else:
        # 过载区 (>1.0): 堵死状态
        # 线性爆炸：每超 10% 负载，排队因子增加 20
        # 例如 util=2.0 (200%) -> queue_factor = 210 -> 时延增加 200ms+
        queue_factor = 10.0 + (util - 1.0) * 200.0
    
    # 封顶防止数值溢出，但 500 倍已经足以让时延从 50ms 变成 25000ms
    queue_factor = min(queue_factor, 500.0)
    
    # 假设基础处理/排队单位时延为 1ms，乘以排队因子
    queuing_delay = 1.0 * queue_factor
    
    dynamic_delay = static_delay + queuing_delay
    
    # 6. 写回状态到图对象
    G[u][v]['loss'] = dynamic_loss
    G[u][v]['delay'] = dynamic_delay
    
    # 标记拥塞 (用于日志统计)
    G[u][v]['is_congested'] = (util > 1.0)