# -*- coding: utf-8 -*-
import sys
import os
import unittest
import networkx as nx

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from src.routing.dijkstra import DijkstraStrategy
from src.routing.iga.iga import IGAStrategy

class TestAlgorithms(unittest.TestCase):
    def setUp(self):
        """构造一个经典的 '拥塞陷阱' 拓扑"""
        self.G = nx.Graph()
        
        # 节点带有坐标 (用于 IGA 方向引导，假设 D 在 (10,10))
        self.G.add_node('S', lat=0, lon=0)
        self.G.add_node('D', lat=10, lon=10)
        self.G.add_node('A', lat=5, lon=5)   # 路径1中间点
        self.G.add_node('B', lat=2, lon=8)   # 路径2中间点1
        self.G.add_node('C', lat=8, lon=2)   # 路径2中间点2
        
        # 路径 1: S -> A -> D (物理距离短，但严重拥塞)
        # 静态 delay 设为 10，但 loss 设为 0.9 (模拟严重拥塞)
        # 或者 load 设为 0.99
        self.G.add_edge('S', 'A', delay=10, distance=10, load=0.1, loss=0.0)
        # 陷阱链路: A->D
        self.G.add_edge('A', 'D', delay=10, distance=10, load=0.99, loss=0.5) 
        
        # 路径 2: S -> B -> C -> D (物理距离长，但空闲)
        self.G.add_edge('S', 'B', delay=10, distance=10, load=0.1, loss=0.0)
        self.G.add_edge('B', 'C', delay=10, distance=10, load=0.1, loss=0.0)
        self.G.add_edge('C', 'D', delay=10, distance=10, load=0.1, loss=0.0)

        self.dijkstra = DijkstraStrategy(weight_key='delay')
        self.iga = IGAStrategy()
        # 调大 IGA 的惩罚参数以确保规避生效
        self.iga.alpha = 0.5 # 关注时延
        self.iga.beta = 0.5  # 关注丢包

    def test_dijkstra_behavior(self):
        """Dijkstra 应该选择跳数最少的路径 (S->A->D)"""
        print("\n[Algo] Testing Dijkstra (Baseline)...")
        path, metrics = self.dijkstra.find_path(self.G, 'S', 'D')
        print(f"   Dijkstra Path: {path}")
        
        # Dijkstra 只看 weight='delay' (都是10)，所以 S-A-D 总耗时 20， S-B-C-D 总耗时 30
        # 它必然选 S-A-D
        expected_path = ['S', 'A', 'D']
        self.assertEqual(path, expected_path)
        print("   -> Dijkstra 掉进了拥塞陷阱 (符合预期)")

    def test_iga_congestion_avoidance(self):
        """IGA 应该能感知 A->D 的高负载/高丢包，从而选择 S->B->C->D"""
        print("\n[Algo] Testing IGA (Proposed)...")
        
        # 运行 IGA
        # 注意：IGA 是随机算法，可能偶尔失败，但在陷阱如此明显的情况下应大概率成功
        # 为了稳定，我们可以运行几次取最优，但在单元测试里我们信赖单次
        path, metrics = self.iga.find_path(self.G, 'S', 'D')
        print(f"   IGA Path: {path}")
        
        expected_path = ['S', 'B', 'C', 'D']
        
        # 验证是否绕开了 A
        self.assertNotIn('A', path, "IGA 未能规避拥塞节点 A")
        self.assertEqual(path, expected_path, "IGA 应选择长但空闲的路径")
        print("   -> IGA 成功规避拥塞 (验证通过)")

if __name__ == '__main__':
    unittest.main()