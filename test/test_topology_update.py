# -*- coding: utf-8 -*-
import sys
import os
import unittest
import networkx as nx

# 路径 Hack
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from src.topology import TopologyManager

class TestTopologyUpdate(unittest.TestCase):
    def setUp(self):
        self.tm = TopologyManager()
        # 创建一个模拟的微型图，而不是加载巨大的 STK 数据
        self.G = nx.Graph()
        # 添加一条边: u -> v, 容量 100 Mbps, 物理时延 10ms
        self.G.add_edge('u', 'v', 
                        capacity=100.0, 
                        used_bw=0.0, 
                        load=0.0, 
                        delay_prop=10.0, 
                        loss_phy=0.001,
                        delay=10.0, 
                        loss=0.001)

    def test_low_load_update(self):
        """测试低负载情况 (BPR 模型下应轻微增时延、轻微增丢包)"""
        print("\n[Test] 低负载状态更新测试...")
        # 增加 20Mbps 流量 (Load = 0.2)
        self.tm.update_link_state(self.G, 'u', 'v', 20.0)
        
        edge = self.G['u']['v']
        print(f"   Load: {edge['load']:.2f}, Delay: {edge['delay']:.2f}ms")
        
        self.assertAlmostEqual(edge['used_bw'], 20.0)
        self.assertAlmostEqual(edge['load'], 0.2)
        self.assertAlmostEqual(edge['loss'], 0.0012)
        expected_delay = 10.0 * (1.0 + (0.2 ** 6))
        self.assertAlmostEqual(edge['delay'], expected_delay)

    def test_high_load_congestion(self):
        """测试高负载情况 (未过载，但已明显增时延/丢包)"""
        print("\n[Test] 高负载拥塞测试...")
        # 增加 90Mbps 流量 (Load = 0.9)
        self.tm.update_link_state(self.G, 'u', 'v', 90.0)
        
        edge = self.G['u']['v']
        print(f"   Load: {edge['load']:.2f}, Delay: {edge['delay']:.2f}ms, Loss: {edge['loss']:.4f}")
        
        self.assertEqual(edge['load'], 0.9)
        self.assertAlmostEqual(edge['loss'], 0.0019)
        self.assertTrue(edge['delay'] > 15.0)
        
    def test_overflow_protection(self):
        """测试过载场景 (当前模型允许超载，用于显式体现拥塞惩罚)"""
        print("\n[Test] 带宽溢出测试...")
        # 增加 150Mbps 流量 (超过 100)
        self.tm.update_link_state(self.G, 'u', 'v', 150.0)
        edge = self.G['u']['v']
        self.assertEqual(edge['used_bw'], 150.0)
        self.assertEqual(edge['load'], 1.5)
        self.assertTrue(edge['loss'] > 0.3)
        self.assertTrue(edge['delay'] > 100.0)

if __name__ == '__main__':
    unittest.main()
