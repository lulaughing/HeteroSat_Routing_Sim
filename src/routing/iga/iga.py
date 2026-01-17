# -*- coding: utf-8 -*-
"""
File: src/routing/iga/iga.py
Description: IGA 主控制器 (回归单目标寻优，依赖外部智能调度)
"""
import random
import numpy as np
import networkx as nx
from src.routing.strategy import RoutingStrategy
from src.utils import get_algo_logger

# 导入子模块 (保持不变，核心智能逻辑)
from .iga_init import initialize_population
from .iga_fitness import calculate_fitness, evaluate_path
from .iga_selection import selection
from .iga_crossover import crossover
from .iga_mutation import mutation

alog = get_algo_logger()

class IGAStrategy(RoutingStrategy):
    def __init__(self, pop_size=20, max_iter=20, pc=0.8, pm=0.2, p_guide=0.8):
        self.pop_size = pop_size
        self.max_iter = max_iter
        self.pc = pc
        self.pm = pm
        self.p_guide = p_guide

    def find_path(self, G, src, dst, constraints):
        """
        IGA 寻路入口
        Args:
            dst: 单个节点 ID (由 simulation_utils 预选好的出口)
        """
        req_id = constraints.get('id', 'N/A')
        
        # 1. 物理连通性检查
        # 此时 dst 是确定的单个节点
        if not nx.has_path(G, src, dst):
            return None, {}

        # 2. 运行遗传算法
        best_path = self.run(G, src, dst, constraints)

        if best_path:
            # metrics = evaluate_path(G, best_path) # 可选，用于调试
            return best_path, {}
        else:
            return None, {}

    def run(self, G, src, dst, constraints):
        req_id = constraints.get('id', 'Unknown')
        
        # 1. 初始化 (使用方向引导 + KSP)
        population = initialize_population(G, src, dst, self.pop_size, self.p_guide)
        if not population: return None

        global_best_path = None
        global_best_fit = -1
        
        alog.debug(f"\n--- [IGA Start] ID={req_id} | {src}->{dst} ---")

        for t in range(self.max_iter):
            # 2. 评估 (包含非线性拥塞惩罚)
            fitness = [calculate_fitness(G, p, constraints) for p in population]
            
            # 记录本代最优
            best_idx = np.argmax(fitness)
            if fitness[best_idx] > global_best_fit:
                global_best_fit = fitness[best_idx]
                global_best_path = population[best_idx]

            # 埋点日志 (记录 Top 3 状态)
            sorted_indices = np.argsort(fitness)[::-1]
            top_k = sorted_indices[:3] 
            
            log_msg = f"Gen {t:2d} | BestFit: {fitness[top_k[0]]:.6f}"
            for rank, idx in enumerate(top_k):
                p_ind = population[idx]
                m = evaluate_path(G, p_ind)
                log_msg += f" | #{rank+1}: D={m['delay']:.0f}, L={m['loss']:.3f}, U={m['max_util']:.2f}"
            
            alog.debug(log_msg)

            # 3. 选择
            selected = selection(population, fitness)

            # 4. 交叉 & 变异 (拥塞感知变异在此触发)
            offspring = []
            while len(offspring) < self.pop_size:
                p1 = random.choice(selected)
                p2 = random.choice(selected)
                
                if random.random() < self.pc:
                    c1, c2 = crossover(G, p1, p2)
                else:
                    c1, c2 = p1, p2
                
                c1 = mutation(G, c1)
                c2 = mutation(G, c2)
                
                offspring.extend([c1, c2])
            
            population = offspring[:self.pop_size]
            if global_best_path: 
                population[0] = global_best_path 

        return global_best_path
