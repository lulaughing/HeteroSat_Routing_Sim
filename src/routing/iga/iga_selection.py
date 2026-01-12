# -*- coding: utf-8 -*-
"""
File: src/routing/iga/iga_selection.py
Description: 选择操作 (锦标赛策略)
"""
import random
from src.utils import get_algo_logger

alog = get_algo_logger()

def selection(population, fitness, k=None):
    """
    锦标赛选择 (Tournament Selection)
    每次随机选几个个体，让其中最好的那个繁殖后代
    """
    if k is None: k = len(population)
    selected = []
    
    # 记录一下选择前的群体状态，用于日志分析
    avg_fit = sum(fitness) / len(fitness) if fitness else 0
    
    for _ in range(k):
        # 随机抽3个打擂台
        indices = random.sample(range(len(population)), min(3, len(population)))
        # 选适应度最高的索引
        winner_idx = max(indices, key=lambda i: fitness[i])
        selected.append(population[winner_idx])
        
    # 抽样打印日志 (避免过于频繁)
    if random.random() < 0.1:
        alog.debug(f"      🧬 [Select] 锦标赛完成. AvgFit: {avg_fit:.6f} -> 保留了 {len(selected)} 个父代")
    
    return selected