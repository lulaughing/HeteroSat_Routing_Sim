# -*- coding: utf-8 -*-
"""
File: src/routing/iga/iga_init.py
Description: 种群初始化 (混合策略: KSP 最短路注入 + 方向引导)
"""
import networkx as nx
import random
import re
from itertools import islice
from src.utils import get_algo_logger, get_lazy_logger

alog = get_lazy_logger(get_algo_logger)

def _calc_manhattan(u, v):
    """计算曼哈顿距离 (辅助方向引导)"""
    try:
        def parse_coord(name):
            digits = re.findall(r'\d+', name)
            if not digits: return (0, 0)
            s = "".join(digits)
            if len(s) >= 4: return int(s[:2]), int(s[2:4])
            return (0, 0)

        if 'Detect' in u: N_orb, N_sat = 10, 10
        else: N_orb, N_sat = 15, 15
        
        if u.split('_')[0] != v.split('_')[0]: return 0 

        o1, p1 = parse_coord(u)
        o2, p2 = parse_coord(v)
        
        d_orb = min(abs(o1 - o2), N_orb - abs(o1 - o2))
        d_sat = min(abs(p1 - p2), N_sat - abs(p1 - p2))
        return d_orb + d_sat
    except:
        return 0

def initialize_population(G, src, dst, pop_size, p_guide=0.8):
    """
    混合初始化策略:
    1. 精英注入: 先生成 K 条最短路径 (保证下限不低于 SGA)
    2. 多样性补充: 剩余个体使用方向引导随机游走 (提供进化潜力)
    """
    population = []
    
    # --- 1. 精英注入 (K-Shortest Paths) ---
    # 占用种群的 1/3，确保 H-IGA 起跑线与 SGA 一致
    k_elite = max(2, int(pop_size * 0.3)) 
    try:
        # 使用 weight='delay' 找到物理最短路
        ksp_gen = nx.shortest_simple_paths(G, src, dst, weight='delay')
        elites = list(islice(ksp_gen, k_elite))
        for p in elites:
            if p not in population:
                population.append(p)
        alog.debug(f"   [Init] KSP 注入: 成功生成 {len(population)} 条精英路径")
    except Exception as e:
        alog.debug(f"   [Init] KSP 注入失败: {e}")

    # --- 2. 方向引导 (Direction Guided Random Walk) ---
    # 填充剩余种群
    attempts = 0
    while len(population) < pop_size and attempts < pop_size * 5:
        attempts += 1
        path = [src]
        curr = src
        visited = {src}
        
        max_hops = 30 # 防止死循环
        
        for _ in range(max_hops):
            if curr == dst: break
            
            neighbors = [n for n in G.neighbors(curr) if n not in visited]
            if not neighbors: break
            
            # 分类邻居
            n_app = [] # 趋近
            n_div = [] # 远离
            curr_dist = _calc_manhattan(curr, dst)
            
            for n in neighbors:
                if _calc_manhattan(n, dst) < curr_dist:
                    n_app.append(n)
                else:
                    n_div.append(n)
            
            # 概率选择
            next_node = None
            if n_app and random.random() < p_guide:
                next_node = random.choice(n_app)
            elif n_div:
                next_node = random.choice(n_div)
            elif n_app:
                next_node = random.choice(n_app)
            
            # 兜底：如果方向引导没路了，随便选一个
            if not next_node and neighbors:
                next_node = random.choice(neighbors)

            if next_node:
                path.append(next_node)
                visited.add(next_node)
                curr = next_node
            else:
                break
        
        if path[-1] == dst:
            if path not in population:
                population.append(path)

    # --- 3. 最终兜底 ---
    # 如果方向引导太难(比如跨层)，导致种群没填满，继续用 KSP (无权/BFS) 填满
    if len(population) < pop_size:
        needed = pop_size - len(population)
        try:
            # 这次用 weight=None (BFS)，找跳数最少的，增加多样性
            bfs_gen = nx.shortest_simple_paths(G, src, dst, weight=None)
            for p in bfs_gen:
                if p not in population:
                    population.append(p)
                    if len(population) >= pop_size: break
        except:
            pass

    return population
