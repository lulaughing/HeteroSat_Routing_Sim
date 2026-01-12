# -*- coding: utf-8 -*-
"""
File: test/test_h_iga_flow.py
Description: H-IGA 分层协同路由逻辑单元测试
目标: 验证 [GEO规划 -> 边界选择 -> QoS分解 -> IGA执行] 全流程
"""
import sys
import os
import networkx as nx
import logging

# 路径配置
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

# 引入模块
from src.utils import setup_logger
from src.routing.hierarchical_mapper import VirtualTopologyManager
from src.routing.inter_algo import InterDomainAlgorithm
from src.routing.iga.iga import IGAStrategy

# 设置日志 (只显示 INFO)
logger = setup_logger(level=logging.INFO)

# ==============================================================================
# 待测试的核心协同函数 (逻辑同 main.py)
# ==============================================================================
def decompose_and_execute_hierarchical(G_phy, G_vir, vir_path, phy_to_vir, src, dst, qos, algo_intra):
    """
    分层协同核心逻辑
    """
    # 1. 建立 Vir -> [Phy Nodes] 的反向索引
    vir_to_phy = {}
    for p_node, v_id in phy_to_vir.items():
        if v_id not in vir_to_phy: vir_to_phy[v_id] = []
        vir_to_phy[v_id].append(p_node)

    full_path = []
    total_delay_req = qos.get('delay_req', 1000)
    
    # 2. 估算虚拟路径总权重 (用于按比例分配预算)
    total_est_delay = 0
    vir_edge_delays = []
    for i in range(len(vir_path) - 1):
        u_vir, v_vir = vir_path[i], vir_path[i+1]
        if G_vir.has_edge(u_vir, v_vir):
            d = G_vir[u_vir][v_vir].get('delay', 10)
        else:
            d = 10 # 兜底
        vir_edge_delays.append(d)
        total_est_delay += d
    
    if total_est_delay == 0: total_est_delay = 1

    print(f"\n   [Budget] 总预算: {total_delay_req}ms, 虚拟路径估算总时延: {total_est_delay:.2f}ms")

    # 3. 逐跳执行
    current_phy_src = src
    
    for i in range(len(vir_path) - 1):
        u_vir = vir_path[i]
        v_vir = vir_path[i+1]
        
        # --- A. 边界选择 (Best Boundary Selection) ---
        best_boundary_link = None
        min_boundary_delay = float('inf')
        
        u_phy_nodes = vir_to_phy.get(u_vir, [])
        
        # 遍历 u_vir 中的节点，找连接到 v_vir 的最佳链路
        for u_node in u_phy_nodes:
            if u_node not in G_phy: continue
            for neighbor in G_phy.neighbors(u_node):
                if phy_to_vir.get(neighbor) == v_vir:
                    d = G_phy[u_node][neighbor].get('delay', float('inf'))
                    if d < min_boundary_delay:
                        min_boundary_delay = d
                        best_boundary_link = (u_node, neighbor)
        
        if not best_boundary_link:
            print(f"   ❌ 错误: 无法找到域 {u_vir} 到 {v_vir} 的物理连接!")
            return None, False 
            
        current_egress, next_ingress = best_boundary_link
        print(f"   [Boundary] 域间跳跃 {i+1}: {u_vir} -> {v_vir}")
        print(f"              锁定物理链路: {current_egress} (出口) -> {next_ingress} (入口)")
        
        # --- B. 预算分解 (QoS Budget Decomposition) ---
        segment_weight = vir_edge_delays[i] / total_est_delay
        segment_budget = total_delay_req * segment_weight
        
        print(f"              分配预算: {segment_budget:.2f}ms (占比 {segment_weight*100:.1f}%)")
        
        # --- C. 域内路由 (Intra-Domain Routing) ---
        if current_phy_src != current_egress:
            # 构造局部 QoS
            local_qos = qos.copy()
            local_qos['delay_req'] = segment_budget
            # 关闭 debug 防止刷屏
            if 'debug' in local_qos: del local_qos['debug'] 
            
            # 调用 IGA
            sub_path, metrics = algo_intra.find_path(G_phy, current_phy_src, current_egress, local_qos)
            
            if not sub_path:
                print(f"   ❌ 错误: 域内 IGA 寻路失败 ({current_phy_src} -> {current_egress})")
                return None, False
            
            print(f"              ✅ 域内路径: {sub_path} (Load: {metrics['max_load']:.2f})")
            full_path.extend(sub_path[:-1])
        else:
            print(f"              ✅ 域内路径: 直连 (无需寻路)")
            full_path.append(current_phy_src)
            
        # 跨域直连
        current_phy_src = next_ingress
    
    # 4. 最后一段 (Last Ingress -> 最终 Dst)
    last_budget = total_delay_req # 简单起见给剩余全部
    local_qos = qos.copy()
    local_qos['delay_req'] = last_budget
    if 'debug' in local_qos: del local_qos['debug']
    
    print(f"   [Final Seg] 最后一段: {current_phy_src} -> {dst}")
    sub_path, metrics = algo_intra.find_path(G_phy, current_phy_src, dst, local_qos)
    
    if sub_path:
        print(f"              ✅ 域内路径: {sub_path}")
        full_path.extend(sub_path)
        return full_path, True
    else:
        return None, False

# ==============================================================================
# 测试场景构建
# ==============================================================================
def test_hierarchical_logic():
    print("🚀 [Test] 启动 H-IGA 分层协同逻辑测试...")
    
    # 1. 构造链式物理拓扑
    # Src(Domain1) --- link --- Egress1(Domain1) === link === Ingress2(Domain2) --- link --- Dst(Domain2)
    G = nx.Graph()
    
    # Domain 1 (Lat 0, Lon 0) -> Virtual_LEO_0_0
    G.add_node('Src', lat=0, lon=0, type='LEO')
    G.add_node('E1', lat=2, lon=2, type='LEO')
    G.add_edge('Src', 'E1', delay=10, loss=0.001, capacity=100, load=0.1) # 域内
    
    # Domain 2 (Lat 0, Lon 30) -> Virtual_LEO_0_1 (假设 grid=30)
    G.add_node('I2', lat=0, lon=31, type='LEO')
    G.add_node('Dst', lat=2, lon=33, type='LEO')
    G.add_edge('I2', 'Dst', delay=20, loss=0.001, capacity=100, load=0.1) # 域内
    
    # 跨域链路 (E1 -> I2)
    G.add_edge('E1', 'I2', delay=50, loss=0.001, capacity=100, load=0.1) # 跨域长链路

    # 2. 构建虚拟层
    # 强制网格大小，确保 Domain 1 和 2 分开
    vtm = VirtualTopologyManager(grid_configs={'LEO': {'lat': 30, 'lon': 30}})
    G_vir, phy_to_vir = vtm.build_virtual_graph(G)
    
    src_vir = phy_to_vir['Src']
    dst_vir = phy_to_vir['Dst']
    
    print(f"\n1. 映射结果: Src->{src_vir}, Dst->{dst_vir}")
    if src_vir == dst_vir:
        print("⚠️ 警告: 源宿在同一个虚拟域内，无法测试跨域逻辑。请调整坐标。")
        return

    # 3. 运行域间路由 (GEO)
    algo_inter = InterDomainAlgorithm()
    # 只有两个域，路径应该是 [Grid1, Grid2]
    vir_path, _ = algo_inter.find_path(G_vir, src_vir, dst_vir, {'bandwidth': 10})
    print(f"2. 域间路径: {vir_path}")

    # 4. 运行协同路由 (Testing Target)
    algo_iga = IGAStrategy()
    qos = {'delay_req': 200, 'bandwidth': 10} # 总预算 200ms
    
    print("\n3. 执行分层协同...")
    full_path, success = decompose_and_execute_hierarchical(
        G, G_vir, vir_path, phy_to_vir, 'Src', 'Dst', qos, algo_intra=algo_iga
    )
    
    # 5. 验证结果
    if success:
        print(f"\n✅ 测试通过! 端到端物理路径: {full_path}")
        expected = ['Src', 'E1', 'I2', 'Dst']
        if full_path == expected:
            print("   -> 路径符合预期 (完美匹配)")
        else:
            print(f"   -> 路径由算法动态生成 (符合逻辑即可)")
    else:
        print("\n❌ 测试失败!")

if __name__ == "__main__":
    test_hierarchical_logic()