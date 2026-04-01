# -*- coding: utf-8 -*-
"""
File: test/test_routing_mechanisms.py
Description: 单元测试 - 验证 MEO 接入拥塞下的算法行为差异 (SGA vs H-IGA)
"""
import sys
import os
import unittest
import random
import networkx as nx

# 添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.routing.sga import SGAStrategy
from src.routing.iga.iga import IGAStrategy

class TestRoutingMechanisms(unittest.TestCase):
    
    def setUp(self):
        """
        构建一个 Y 型拓扑 (符合论文架构：LEO虚拟域 + MEO物理节点)
        S (源LEO) -> A (拥塞的近LEO出口) -> MEO
                  -> B (空闲的远LEO出口) -> MEO
        """
        self.G_phy = nx.Graph()
        
        # MEO 物理节点 (瓶颈目标)
        self.G_phy.add_node('MEO_01', type='MEO') 
        
        # LEO 物理节点 (同属一个虚拟域)
        self.G_phy.add_node('LEO_S', type='LEO', lat=0, lon=0) 
        self.G_phy.add_node('LEO_A', type='LEO', lat=0, lon=1) # 离S近 (Delay 10)
        self.G_phy.add_node('LEO_B', type='LEO', lat=0, lon=2) # 离S远 (Delay 50)
        
        # 构建链路 (初始化带宽 100Mbps)
        # 1. 域内链路 ISL
        self.G_phy.add_edge('LEO_S', 'LEO_A', capacity=100, used_bw=0, delay=10, loss=0.001)
        self.G_phy.add_edge('LEO_S', 'LEO_B', capacity=100, used_bw=0, delay=50, loss=0.001)
        
        # 2. 接入链路 IOL (出口)
        # 假设 A 和 B 离 MEO 的距离差不多，主要差异在 LEO 内部
        self.G_phy.add_edge('LEO_A', 'MEO_01', capacity=100, used_bw=0, delay=10, loss=0.001) 
        self.G_phy.add_edge('LEO_B', 'MEO_01', capacity=100, used_bw=0, delay=10, loss=0.001) 
        
        # 模拟 TopologyManager 的更新逻辑
        class MockTopologyManager:
            @staticmethod
            def update_link_state(G, u, v, bw):
                if G.has_edge(u, v):
                    G[u][v]['used_bw'] += bw
                    util = G[u][v]['used_bw'] / G[u][v]['capacity']
                    if util > 1.0:
                        G[u][v]['loss'] = 0.9
                    elif util > 0.8:
                        G[u][v]['loss'] = 0.1
                    else:
                        G[u][v]['loss'] = 0.001

        self.topo_mgr = MockTopologyManager()
        random.seed(20260320)

    def test_01_meo_congestion_avoidance(self):
        """
        场景验证：
        当最近的出口 A->MEO 发生严重拥塞时：
        - SGA (无拥塞感知) 依然选择走 A (因为物理总时延短 20ms vs 60ms)
        - H-IGA (有拥塞感知) 应该绕行走 B (虽然慢，但可靠)
        """
        print("\n[Test] 验证 MEO 接入拥塞规避机制...")
        
        # 1. 制造拥塞: 把 LEO_A -> MEO_01 堵死 (模拟之前业务已占满)
        self.topo_mgr.update_link_state(self.G_phy, 'LEO_A', 'MEO_01', 120) # 120Mbps, Util=1.2
        
        print(f"   > Link A->MEO Util: {self.G_phy['LEO_A']['MEO_01']['used_bw']}% (Congested)")
        print(f"   > Link B->MEO Util: {self.G_phy['LEO_B']['MEO_01']['used_bw']}% (Free)")
        
        # 3. 业务需求
        req = {'bandwidth': 10, 'delay_req': 1000, 'loss_req': 0.01}
        
        # --- 运行 SGA ---
        # 预期: SGA 仍更偏向最近出口 A
        print("\n   [Running SGA]...")
        sga = SGAStrategy()
        path_sga, _ = sga.find_path(self.G_phy, 'LEO_S', 'MEO_01', req)
        print(f"   > SGA Decision: {path_sga}")
        
        self.assertEqual(path_sga, ['LEO_S', 'LEO_A', 'MEO_01'])
        
        # --- 运行 H-IGA ---
        # 预期: IGA 规避已过载的出口 A，改走 B
        print("\n   [Running H-IGA]...")
        iga = IGAStrategy()
        path_iga, _ = iga.find_path(self.G_phy, 'LEO_S', 'MEO_01', req)
        print(f"   > H-IGA Decision: {path_iga}")
        
        self.assertIn('LEO_B', path_iga, "H-IGA 失败：未能规避拥塞节点 A，请检查适应度函数参数！")
        self.assertNotIn('LEO_A', path_iga, "H-IGA 不应继续走拥塞出口 A")
        
        print("\n   验证通过：算法行为差异符合预期。")

if __name__ == '__main__':
    unittest.main()
