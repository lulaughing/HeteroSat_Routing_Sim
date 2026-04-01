# -*- coding: utf-8 -*-
"""
File: test/test_congestion_scenario.py
Description: 单元测试 - 验证"局部极端拥塞"场景的构建有效性
"""
import sys
import os
import unittest
import networkx as nx
from collections import Counter

# 添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.topology import TopologyManager
from src.traffic import TrafficGenerator
from src.simulation_utils import manage_traffic, SERVICE_TYPES, ensure_dir

class TestCongestionScenario(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        print("\n=== 初始化拓扑与流量环境 ===")
        cls.topo_mgr = TopologyManager()
        cls.traffic_gen = TrafficGenerator(cls.topo_mgr)
        cls.time_step = 0
        cls.req_count = 1000
        cls.G = cls.topo_mgr.get_graph_at_time(cls.time_step)
        
        # 生成流量 (强制重新生成)
        traffic_dir = "data/test_traffic"
        ensure_dir(traffic_dir)
        # 删除旧文件以确保逻辑更新
        json_path = os.path.join(traffic_dir, f"requests_T{cls.time_step}_N{cls.req_count}.json")
        if os.path.exists(json_path):
            os.remove(json_path)
            
        cls.requests = manage_traffic(cls.traffic_gen, cls.G, cls.time_step, cls.req_count, traffic_dir)

    def test_01_topology_bottleneck(self):
        """测试 1: 物理链路带宽是否符合当前模型配置 (100/60 Mbps)"""
        print("\n[Test 1] 检查物理带宽限制...")
        
        meo_links = []
        detect_meo_links = []
        
        for u, v, d in self.G.edges(data=True):
            type_u = self.G.nodes[u].get('type')
            type_v = self.G.nodes[v].get('type')
            
            # MEO-MEO 骨干
            if type_u == 'MEO' and type_v == 'MEO':
                meo_links.append(d['capacity'])
            
            # Detect-MEO 接入
            if ('Detect' in [type_u, type_v]) and ('MEO' in [type_u, type_v]):
                detect_meo_links.append(d['capacity'])
                
        # 验证 MEO 骨干带宽
        if meo_links:
            avg_cap = sum(meo_links)/len(meo_links)
            print(f"   > MEO-MEO 平均带宽: {avg_cap} Mbps (期望: 100)")
            self.assertTrue(all(c <= 100 for c in meo_links), "MEO骨干带宽未正确限制！")
            
        # 验证接入带宽
        if detect_meo_links:
            avg_cap = sum(detect_meo_links)/len(detect_meo_links)
            print(f"   > Detect-MEO 平均带宽: {avg_cap} Mbps (期望: 60)")
            self.assertTrue(all(c <= 60 for c in detect_meo_links), "接入链路带宽未正确限制！")

    def test_02_traffic_composition(self):
        """测试 2: 业务比例是否符合当前加权随机配置"""
        print("\n[Test 2] 检查业务类型分布...")
        
        type_counts = Counter([r['service_type'] for r in self.requests])
        total = len(self.requests)
        
        print(f"   > 业务分布: {dict(type_counts)}")
        
        # 验证 Remote_Sensing 比例
        sensing_ratio = type_counts.get('Remote_Sensing', 0) / total
        print(f"   > Remote_Sensing 占比: {sensing_ratio:.2%} (期望: ~20%)")
        self.assertGreater(sensing_ratio, 0.15, "高带宽业务比例不足！")

    def test_03_traffic_corridor(self):
        """测试 3: 流量是否集中在地理走廊 (北美->东亚)"""
        print("\n[Test 3] 检查流量走廊地理分布...")
        
        src_lons = []
        dst_lons = []
        
        for req in self.requests:
            src_node = self.G.nodes[req['src']]
            dst_node = self.G.nodes[req['dst']]
            src_lons.append(src_node['lon'])
            dst_lons.append(dst_node['lon'])
            
        # 简单验证：源节点大部分在西半球 (-130 ~ -80)，宿节点在东半球 (100 ~ 150)
        west_src = sum(1 for lon in src_lons if -140 <= lon <= -70)
        east_dst = sum(1 for lon in dst_lons if 90 <= lon <= 160)
        
        print(f"   > 源节点在走廊区域占比: {west_src/len(src_lons):.2%}")
        print(f"   > 宿节点在走廊区域占比: {east_dst/len(dst_lons):.2%}")
        
        # 允许有 20% 的背景随机流量，所以阈值设为 0.7
        self.assertGreater(west_src/len(src_lons), 0.7, "源节点未集中在走廊区域！")

    def test_04_alternative_paths_check(self):
        """
        测试 4: 关键测试 - 拥塞节点是否有备选路径？
        这是 H-IGA 能否生效的物理前提。
        """
        print("\n[Test 4] 检查拥塞节点的多样性 (H-IGA 生效前提)...")
        
        # 找到被大量业务作为源的 Detect 节点
        src_counts = Counter([r['src'] for r in self.requests if r['service_type'] == 'Remote_Sensing'])
        top_src = src_counts.most_common(3)
        
        for src, count in top_src:
            neighbors = list(self.G.neighbors(src))
            # 筛选出上层 MEO 邻居
            meo_neighbors = [n for n in neighbors if 'MEO' in n]
            
            print(f"   > 热点源节点 {src} (发出 {count} 条重业务):")
            print(f"     - 可见 MEO 邻居数: {len(meo_neighbors)} -> {meo_neighbors}")
            
            # 如果只有一个 MEO 邻居，H-IGA 也没辙
            if len(meo_neighbors) < 2:
                print(f"     警告: 物理瓶颈！该节点只有 1 个上行出口，算法无法规避拥塞。")
            else:
                print(f"     通过: 存在多路径 ({len(meo_neighbors)} 条)，算法有优化空间。")

if __name__ == '__main__':
    unittest.main()
