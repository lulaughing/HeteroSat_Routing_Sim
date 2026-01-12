# -*- coding: utf-8 -*-
import sys
import os
import unittest
import networkx as nx

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from src.routing.hierarchical_mapper import VirtualTopologyManager

class TestVirtualMapper(unittest.TestCase):
    def setUp(self):
        # 设定网格步长: Lat 10度, Lon 10度
        self.vtm = VirtualTopologyManager(grid_configs={'LEO': {'lat': 10, 'lon': 10}})
        self.G_phy = nx.Graph()

    def test_node_mapping(self):
        """测试物理节点到虚拟节点的映射"""
        # 两个物理节点在同一个网格内 (0, 0)
        self.G_phy.add_node('LEO1', type='LEO', lat=1.0, lon=1.0)
        self.G_phy.add_node('LEO2', type='LEO', lat=5.0, lon=5.0)
        # 一个物理节点在另一个网格 (1, 1)
        self.G_phy.add_node('LEO3', type='LEO', lat=15.0, lon=15.0)
        
        # 构建虚拟图
        G_vir, mapping = self.vtm.build_virtual_graph(self.G_phy)
        
        print(f"\n[Mapper] 虚拟节点列表: {list(G_vir.nodes())}")
        
        # 验证 LEO1 和 LEO2 映射到了同一个 ID
        self.assertEqual(mapping['LEO1'], mapping['LEO2'])
        # 验证 LEO3 映射到了不同的 ID
        self.assertNotEqual(mapping['LEO1'], mapping['LEO3'])

    def test_link_aggregation(self):
        """测试虚边属性聚合 (Min BW, Avg Delay)"""
        # 构造场景：
        # 网格A (包含 A1, A2) --- 网格B (包含 B1)
        # 物理链路1: A1-B1 (BW=100, D=10)
        # 物理链路2: A2-B1 (BW=50, D=20)
        
        self.G_phy.add_node('A1', type='LEO', lat=1.0, lon=1.0)
        self.G_phy.add_node('A2', type='LEO', lat=2.0, lon=2.0)
        self.G_phy.add_node('B1', type='LEO', lat=15.0, lon=15.0) # 另一个网格
        
        self.G_phy.add_edge('A1', 'B1', capacity=100, delay=10, loss=0.01)
        self.G_phy.add_edge('A2', 'B1', capacity=50,  delay=20, loss=0.05)
        
        G_vir, _ = self.vtm.build_virtual_graph(self.G_phy)
        
        # 找到连接两个虚拟节点的虚边
        u = list(G_vir.nodes())[0]
        v = list(G_vir.nodes())[1]
        edge = G_vir[u][v]
        
        print(f"\n[Mapper] 聚合虚边属性: BW={edge['capacity']}, Delay={edge['delay']}, Loss={edge['loss']}")
        
        # 验证聚合逻辑
        # 带宽取最小 (瓶颈) -> 50
        self.assertEqual(edge['capacity'], 50)
        # 时延取平均 -> (10+20)/2 = 15
        self.assertEqual(edge['delay'], 15)
        # 丢包取最大 -> 0.05
        self.assertEqual(edge['loss'], 0.05)

if __name__ == '__main__':
    unittest.main()