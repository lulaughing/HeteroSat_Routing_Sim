# -*- coding: utf-8 -*-
"""
File: src/routing/strategy.py
Description: 路由算法基类接口 (统一标准版)
"""
from abc import ABC, abstractmethod

class RoutingStrategy(ABC):
    def __init__(self):
        self.name = "Base"

    @abstractmethod
    def find_path(self, G, src, dst, constraints=None):
        """
        在拓扑图 G 中寻找从 src 到 dst 的路径
        
        Args:
            G: NetworkX graph (带权有向图/无向图)
            src: 源节点 ID
            dst: 目的节点 ID
            constraints: (可选) QoS 约束字典 {'bandwidth': 10, 'delay_req': 200, ...}
            
        Returns:
            path: 节点列表 [src, n1, n2, ..., dst] 或 None (未找到)
            metrics: 字典 {'cost': float, 'delay': float, ...}
        """
        pass