# -*- coding: utf-8 -*-
"""
File: src/routing/iga/iga_crossover.py
Description: 交叉操作 (完全复现论文双模交叉策略: 节点交换 + 断点修补)
"""
import random
import networkx as nx
from src.utils import get_algo_logger

alog = get_algo_logger()

def crossover(G, p1, p2):
    """
    双模交叉策略 (Thesis 4.4.4)
    输入: 图 G, 父代路径 p1, p2
    输出: 子代路径 c1, c2
    
    逻辑:
    1. 优先尝试 [中间节点交换法]: 利用公共节点交换片段。
    2. 失败则使用 [修复式重组法]: 随机截断，利用最短路修复剩余段。
    """
    # 路径太短无法交叉，直接返回
    if len(p1) < 3 or len(p2) < 3:
        return p1, p2

    # --- 策略 1: 中间节点交换法 (Preferred) ---
    # 寻找除起点终点外的公共节点
    common = set(p1[1:-1]) & set(p2[1:-1])
    
    if common:
        node = random.choice(list(common))
        idx1 = p1.index(node)
        idx2 = p2.index(node)
        
        # 交换片段: P1前段 + P2后段
        c1 = p1[:idx1] + p2[idx2:]
        # 交换片段: P2前段 + P1后段
        c2 = p2[:idx2] + p1[idx1:]
        
        if random.random() < 0.05: 
            alog.debug(f"      ❌ [Cross-1] 节点交换 {node}")
        return c1, c2
        
    # --- 策略 2: 断点修补/重组法 (Fallback) ---
    # 对应论文中的"方向序列重组+边界修复"
    # 实现逻辑: 截断路径，保留前半段，后半段重新寻路(修复)以保证物理连通
    else:
        try:
            # 随机选择切断点 (保留前半段)
            cut1 = random.randint(1, len(p1) - 2)
            cut2 = random.randint(1, len(p2) - 2)
            
            # 断点节点
            u1 = p1[cut1]
            u2 = p2[cut2]
            
            # 终点
            dst = p1[-1]
            
            # 尝试修复: 从断点 u1/u2 找一条去 dst 的路
            # 使用 weight='delay' 保证修复的路径质量较高 (趋向于选择低时延路径)
            # 这一步模拟了论文中"修正方向序列使其能够到达终点"的过程
            repair1 = nx.shortest_path(G, u1, dst, weight='delay')
            repair2 = nx.shortest_path(G, u2, dst, weight='delay')
            
            # 拼接: 父代前缀 + 修复后缀
            # p1[:cut1] 是 [... u1_prev], repair1 是 [u1, ... dst]
            c1 = p1[:cut1] + repair1
            c2 = p2[:cut2] + repair2
            
            if random.random() < 0.05:
                alog.debug(f"      🔧 [Cross-2] 断点修补: {u1}->Dst, {u2}->Dst")
                
            return c1, c2
            
        except (nx.NetworkXNoPath, Exception):
            # 修复失败(物理不可达)，放弃交叉，返回原父代
            return p1, p2