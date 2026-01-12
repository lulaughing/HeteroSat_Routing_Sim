# -*- coding: utf-8 -*-
"""
File: test/test_integration_full.py
Description: 全流程集成测试
目标: 验证 业务生成 -> 虚拟映射 -> 域间路由 -> 域内路由 -> 性能统计 的完整闭环
"""
import sys
import os
import networkx as nx
import logging

# 路径 Hack
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

# 引入模块
from src.utils import setup_logger
from src.routing.hierarchical_mapper import VirtualTopologyManager
from src.routing.inter_algo import InterDomainAlgorithm
from src.routing.iga.iga import IGAStrategy

# 配置控制台只显示 INFO，但我们在代码里手动打印关键步骤
logger = setup_logger(level=logging.INFO)

def create_mock_topology():
    """
    构造一个简单的跨域物理拓扑
    结构: [域1: SatA] ---1000km--- [域2: SatB] ---1000km--- [域3: SatC]
    """
    G = nx.Graph()
    
    # 1. 添加节点 (分布在不同经度，导致处于不同虚拟网格)
    # 假设网格步长是 Lon 30度
    # SatA @ Lon 10 (Grid_0_0)
    # SatB @ Lon 40 (Grid_0_1)
    # SatC @ Lon 70 (Grid_0_2)
    G.add_node('SatA', type='LEO', lat=0, lon=10, alt=1000)
    G.add_node('SatB', type='LEO', lat=0, lon=40, alt=1000)
    G.add_node('SatC', type='LEO', lat=0, lon=70, alt=1000)
    
    # 2. 添加链路 (物理属性)
    # 链路 A-B
    G.add_edge('SatA', 'SatB', 
               distance=1000, delay=3.33, loss=0.001, capacity=1000, 
               load=0.0, used_bw=0)
    # 链路 B-C
    G.add_edge('SatB', 'SatC', 
               distance=1000, delay=3.33, loss=0.001, capacity=1000, 
               load=0.0, used_bw=0)
               
    return G

def test_full_flow():
    print("\n" + "="*50)
    print("🚀 启动端到端集成测试 (End-to-End Test)")
    print("="*50)

    # 1. 准备环境
    G_phy = create_mock_topology()
    vtm = VirtualTopologyManager(grid_configs={'LEO': {'lat': 30, 'lon': 30}})
    algo_inter = InterDomainAlgorithm()
    algo_iga = IGAStrategy()
    
    src = 'SatA'
    dst = 'SatC'
    qos = {'bandwidth': 50, 'delay_req': 100, 'debug': True} # 开启debug看IGA日志

    print(f"\n[Step 1] 业务请求: {src} -> {dst}")
    print(f"         QoS需求: Bandwidth=50Mbps")

    # 2. 虚拟映射 (Virtual Mapping)
    print("\n[Step 2] 构建虚拟拓扑 (GEO View)...")
    G_vir, phy_to_vir = vtm.build_virtual_graph(G_phy)
    
    src_vir = phy_to_vir[src]
    dst_vir = phy_to_vir[dst]
    print(f"   - 物理源 {src} 映射为 -> {src_vir}")
    print(f"   - 物理宿 {dst} 映射为 -> {dst_vir}")
    
    # 打印一下虚拟边看看
    for u, v, data in G_vir.edges(data=True):
        print(f"   - 虚边 {u}<->{v}: Cap={data['capacity']}, Delay={data['delay']:.2f}")

    # 3. 域间路由 (Inter-Domain Routing)
    print("\n[Step 3] 执行域间路由 (Macro Planning)...")
    vir_path, vir_metrics = algo_inter.find_path(G_vir, src_vir, dst_vir, qos)
    
    if vir_path:
        print(f"✅ 域间规划成功! 虚拟路径: {vir_path}")
        print(f"   - 预估跳数: {len(vir_path)}")
    else:
        print("❌ 域间规划失败!")
        return

    # 4. 域内路由 (Intra-Domain Routing)
    # 只有当域间规划通过，才执行物理层寻路
    print("\n[Step 4] 执行域内路由 (Micro Execution - IGA)...")
    
    # 注意：在真实分层中是分段执行，这里为了测试全网连通性，直接在物理图上跑 IGA
    # 但有了域间规划的保证，我们知道宏观方向是通的
    phy_path, phy_metrics = algo_iga.find_path(G_phy, src, dst, qos)
    
    if phy_path:
        print(f"✅ 物理寻路成功! 物理路径: {phy_path}")
    else:
        print("❌ 物理寻路失败!")
        return

    # 5. 端到端统计 (E2E Statistics)
    print("\n[Step 5] 端到端性能统计...")
    # 使用 IGA 的评估函数来计算最终指标
    final_stats = algo_iga._evaluate_path(G_phy, phy_path)
    
    print(f"   📊 最终时延: {final_stats['delay']:.2f} ms")
    print(f"   📊 最终丢包: {final_stats['loss']:.4f}")
    print(f"   📊 路径负载峰值: {final_stats['max_load']:.2f}")

    print("\n" + "="*50)
    print("🎉 测试完成!")
    print("="*50)

if __name__ == "__main__":
    test_full_flow()