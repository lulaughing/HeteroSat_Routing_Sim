# -*- coding: utf-8 -*-
"""
File: src/routing/sga.py
Description: 标准遗传算法 (SGA) - 极速优化版 (无KSP，无拥塞感知)
"""
import random
import networkx as nx
import numpy as np
from src.routing.strategy import RoutingStrategy

class SGAStrategy(RoutingStrategy):
    def __init__(self, pop_size=40, max_iter=30, pc=0.8, pm=0.2):
        # [优化] 减少 max_iter (15->10)，因为 SGA 陷入拥塞后很难进化出来，跑久了浪费时间
        self.pop_size = pop_size
        self.max_iter = max_iter
        self.pc = pc
        self.pm = pm

    def find_path(self, G, src, dst, constraints):
        # 1. 连通性检查
        if not nx.has_path(G, src, dst):
            return None, {}

        # 2. 运行 SGA
        best_path = self.run(G, src, dst, constraints)

        if best_path:
            return best_path, {}
        else:
            return None, {}

    def run(self, G, src, dst, constraints):
        # --- 1. 极速初始化 (移除 KSP) ---
        population = []
        
        # 种子 1: 物理最短路 (Dijkstra)
        # 这通常是 SGA 的最优解，也是导致它撞墙的原因
        try:
            seed = nx.shortest_path(G, src, dst, weight='delay')
            population.append(seed)
        except:
            return None
            
        # 种子 2~N: 基于种子的随机扰动 (Random Walk)
        # 避免计算 KSP，大幅提速
        attempts = 0
        while len(population) < self.pop_size and attempts < 50:
            attempts += 1
            mutated = self._mutation(G, seed)
            # 简单的去重
            if len(mutated) != len(seed): 
                population.append(mutated)
        
        # 填满
        while len(population) < self.pop_size:
            population.append(list(seed))

        global_best = seed
        global_fit = self._calc_fitness(G, seed, constraints)
        
        # --- 迭代进化 ---
        for t in range(self.max_iter):
            fitness = []
            for p in population:
                f = self._calc_fitness(G, p, constraints)
                fitness.append(f)
            
            best_idx = np.argmax(fitness)
            if fitness[best_idx] > global_fit:
                global_fit = fitness[best_idx]
                global_best = population[best_idx]

            # 简化的轮盘赌
            # 为了速度，直接随机选择父代，不搞复杂的锦标赛
            offspring = []
            # 精英保留
            offspring.append(global_best)
            
            # 生成子代
            while len(offspring) < self.pop_size:
                # 随机选两个父代
                p1 = population[random.randint(0, len(population)-1)]
                p2 = population[random.randint(0, len(population)-1)]
                
                c1, c2 = p1, p2
                if random.random() < self.pc:
                    c1, c2 = self._crossover(p1, p2)
                
                c1 = self._mutation(G, c1)
                c2 = self._mutation(G, c2)
                offspring.extend([c1, c2])
            
            population = offspring[:self.pop_size]

        return global_best

    def _calc_fitness(self, G, path, constraints):
        """
        SGA 适应度: 简单倒数，不包含非线性拥塞惩罚 (作为基线对比)
        """
        delay = 0
        min_bw = float('inf')
        
        for u, v in zip(path[:-1], path[1:]):
            if G.has_edge(u, v):
                d = G[u][v]
                delay += d.get('delay', 10)
                rem = d.get('capacity', 200) - d.get('used_bw', 0)
                if rem < min_bw: min_bw = rem
            else:
                return 1e-15
        
        req_bw = constraints.get('bandwidth', 0)
        req_delay = constraints.get('delay_req', float('inf'))
        
        # 硬约束检查
        if min_bw < req_bw or delay > req_delay:
            return 1e-10
            
        return 1.0 / (delay + 1e-5)

    def _crossover(self, p1, p2):
        # 简单的单点交叉
        common = set(p1[1:-1]) & set(p2[1:-1])
        if common:
            node = random.choice(list(common))
            try:
                idx1 = p1.index(node)
                idx2 = p2.index(node)
                return p1[:idx1] + p2[idx2:], p2[:idx2] + p1[idx1:]
            except: pass
        return p1, p2

    def _mutation(self, G, path):
        # 随机变异: 随机找两点，用最短路重连
        if len(path) < 4: return path
        if random.random() > self.pm: return path
        try:
            idx1 = random.randint(0, len(path)-3)
            idx2 = random.randint(idx1+2, len(path)-1)
            u, v = path[idx1], path[idx2]
            # 变异使用无权 BFS，增加跳数上的多样性，且速度最快
            sub = nx.shortest_path(G, u, v) 
            return path[:idx1] + sub + path[idx2+1:]
        except: return path