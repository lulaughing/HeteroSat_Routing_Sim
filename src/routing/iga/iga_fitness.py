# -*- coding: utf-8 -*-
"""
File: src/routing/iga/iga_fitness.py
Description: 适应度计算 (集成动态 QoS 权重 + 拥塞感知)
对应论文: 4.4.3 节
"""
import math

# [归一化常数]
D_MAX = 2000.0 
L_MAX = 0.1    
LAMBDA = 1.0   
GAMMA = 3.0    # 拥塞敏感度

def get_qos_weights(service_type):
    """
    [新增] 根据业务类型动态调整权重
    保持与域间路由 (InterAlgo) 一致的逻辑
    """
    if service_type in ['Video_Live', 'Voice_VoIP', 'Telemetry_Control']:
        return 0.8, 0.2 # alpha (时延), beta (丢包)
    elif service_type == 'Remote_Sensing':
        return 0.2, 0.8
    else:
        return 0.5, 0.5

def evaluate_path(G, path):
    """
    计算路径物理指标 (通用工具)
    """
    total_delay = 0
    success_prob = 1.0
    min_bw = float('inf')
    max_util = 0.0
    
    for u, v in zip(path[:-1], path[1:]):
        if G.has_edge(u, v):
            attr = G[u][v]
            
            # 1. 时延累加
            total_delay += attr.get('delay', 10)
            
            # 2. 丢包率概率乘积 (1 - 成功率)
            l_loss = attr.get('loss', 0.001)
            # 钳位
            l_loss = max(0.0, min(1.0, l_loss))
            success_prob *= (1.0 - l_loss)
            
            # 3. 带宽与利用率
            cap = attr.get('capacity', 200)
            used = attr.get('used_bw', 0)
            rem = cap - used
            if rem < min_bw: min_bw = rem
            
            util = used / cap if cap > 0 else 1.0
            if util > max_util: max_util = util
    
    total_loss = 1.0 - success_prob
            
    return {
        'delay': total_delay, 
        'loss': total_loss, 
        'min_bw': min_bw,
        'max_util': max_util
    }

def calculate_fitness(G, path, constraints):
    """
    IGA 适应度计算 (动态权重版)
    """
    if not path: return 1e-15
    
    m = evaluate_path(G, path)
    
    # [核心修改] 获取动态权重
    service_type = constraints.get('service_type', 'Unknown')
    alpha, beta = get_qos_weights(service_type)
    
    # 1. 拥塞感知代价 (Cost Function)
    # Cost = (alpha * norm_D + beta * norm_L) * (1 + lambda * exp(gamma * rho))
    base_qos = (alpha * (m['delay'] / D_MAX)) + (beta * (m['loss'] / L_MAX))
    
    # 钳位利用率，防止 exp 溢出
    safe_util = min(m['max_util'], 5.0) 
    cong_penalty = 1.0 + LAMBDA * math.exp(GAMMA * safe_util)
    
    total_cost = base_qos * cong_penalty
    
    # 转化为适应度 (反比)
    f_base = 1.0 / (total_cost + 1e-5)
    
    # 2. 软约束惩罚 (Soft Constraints)
    # [优化] 带宽不足 -> 从毁灭性打击改为极强惩罚 (软约束)
    # 允许算法在绝境下选择拥塞路径，而不是直接放弃
    req_bw = constraints.get('bandwidth', 0)
    bw_penalty_coef = 1.0
    
    if m['min_bw'] < req_bw:
        # return 1e-15 # 原逻辑: 直接淘汰
        # 新逻辑: 适应度降低 100~1000 倍
        shortage = req_bw - m['min_bw']
        # 惩罚系数 = 0.05 / (1 + 缺口) -> [微调] 放宽惩罚力度，从 0.001 提至 0.05
        # 让算法更敢于尝试那些“只缺一点点带宽”的路径
        bw_penalty_coef = 0.05 / (1.0 + shortage)
        
    # 时延超标 -> 渐进式惩罚
    req_delay = constraints.get('delay_req', float('inf'))
    delay_penalty_coef = 1.0
    
    if m['delay'] > req_delay:
        violation = (m['delay'] - req_delay) / (req_delay + 1e-5)
        delay_penalty_coef = 0.1 / (1.0 + violation * 10.0) 
        
    return f_base * bw_penalty_coef * delay_penalty_coef