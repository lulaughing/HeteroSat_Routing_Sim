# -*- coding: utf-8 -*-
"""
File: test/test_geo_planning.py
Description: GEO 主控逻辑验证 (带全网分域概览)
"""
import sys
import os
import networkx as nx
import random
from collections import defaultdict

# 路径 Hack
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from src.topology import TopologyManager
from src.routing.hierarchical_mapper import VirtualTopologyManager
from src.routing.inter_algo import InterDomainAlgorithm

def print_global_partition_stats(G_vir, phy_to_vir, G_phy):
    """
    [新增功能] 打印全网分域情况
    """
    print("\n" + "="*60)
    print("🌍 [Global View] 全网分域情况概览 (Virtual Topology)")
    print("="*60)
    
    # 1. 反向索引: 虚拟域 -> [物理节点列表]
    vir_to_phy = defaultdict(list)
    for p_node, v_id in phy_to_vir.items():
        if p_node in G_phy: # 只统计当前存在的物理节点
            vir_to_phy[v_id].append(p_node)
            
    # 2. 统计各层级域的数量
    domain_types = defaultdict(int)
    domain_loads = [] # 记录每个域包含的物理节点数
    
    for v_id in G_vir.nodes():
        # 简单分类
        if "Virtual_LEO" in v_id: dtype = "LEO_Grid"
        elif "Detect" in v_id: dtype = "Detect_Grid" # 如果Detect也分网格的话
        elif "Facility" in v_id or "Ground" in v_id: dtype = "Ground_Station"
        elif "GEO" in v_id: dtype = "GEO_Sat"
        elif "MEO" in v_id: dtype = "MEO_Sat"
        else: dtype = "Other"
        
        domain_types[dtype] += 1
        count = len(vir_to_phy.get(v_id, []))
        domain_loads.append(count)

    print(f"1. 域 (Domain) 总数: {G_vir.number_of_nodes()}")
    print(f"   - 虚拟链路总数  : {G_vir.number_of_edges()}")
    
    print(f"\n2. 域类型分布:")
    for dtype, count in domain_types.items():
        print(f"   - {dtype:<15}: {count} 个")

    print(f"\n3. 域内聚合度统计 (每个域包含多少物理节点):")
    print(f"   - 最大聚合数: {max(domain_loads) if domain_loads else 0}")
    print(f"   - 平均聚合数: {sum(domain_loads)/len(domain_loads) if domain_loads else 0:.2f}")

    print(f"\n4. 典型域采样 (Sample Inspection):")
    # 采样一个包含节点最多的 LEO 域
    sorted_domains = sorted(vir_to_phy.items(), key=lambda x: len(x[1]), reverse=True)
    
    # 找几个典型的打印看看
    samples_shown = 0
    for v_id, p_nodes in sorted_domains:
        if "Virtual_LEO" in v_id:
            print(f"   🔹 [LEO Grid] {v_id}: 包含 {len(p_nodes)} 颗卫星")
            print(f"      -> {p_nodes}")
            samples_shown += 1
            if samples_shown >= 2: break
            
    # 找一个地面站域
    for v_id, p_nodes in sorted_domains:
        if "Facility" in str(p_nodes):
            print(f"   🔹 [Ground]   {v_id}: {p_nodes}")
            break

    print("="*60 + "\n")

def test_geo_instruction_dispatch():
    print("🚀 [Test] 启动 GEO 主控逻辑验证...")
    
    # 1. 加载物理环境
    tm = TopologyManager()
    G_phy = tm.get_graph_at_time(0) # t=0
    
    # 2. 构建虚拟视图
    vtm = VirtualTopologyManager()
    G_vir, phy_to_vir = vtm.build_virtual_graph(G_phy)

    # ==========================================
    # [新增] 在算路前，先打印分域情况
    # ==========================================
    print_global_partition_stats(G_vir, phy_to_vir, G_phy)

    # 3. 构造业务 (同上)
    src_candidates = [n for n, d in G_phy.nodes(data=True) if d['type'] in ['Detect', 'LEO']]
    dst_candidates = [n for n, d in G_phy.nodes(data=True) if d['type'] == 'Ground']
    
    if not src_candidates or not dst_candidates:
        print("❌ 节点不足，无法测试。")
        return

    # 随机找一对跨域的
    src, dst = src_candidates[0], dst_candidates[0]
    for _ in range(50):
        s = random.choice(src_candidates)
        d = random.choice(dst_candidates)
        if phy_to_vir.get(s) != phy_to_vir.get(d):
            src, dst = s, d
            break

    src_vir = phy_to_vir.get(src)
    dst_vir = phy_to_vir.get(dst)
    
    print(f"📨 [Request] 业务请求: {src} ({src_vir}) -> {dst} ({dst_vir})")

    # 4. GEO 执行域间路由
    algo_inter = InterDomainAlgorithm()
    vir_path, metrics = algo_inter.find_path(G_vir, src_vir, dst_vir, {'bandwidth': 10})
    
    if not vir_path:
        print("❌ 域间路由规划失败！")
        return

    print(f"🗺️ [GEO Routing] 域间路径: {vir_path} (Est Delay: {metrics['delay']:.2f}ms)")

    # 5. 模拟 GEO 信息下发 (同上一次代码，略微简化打印)
    print(f"\n📡 [GEO Dispatch] 下发指令详情:")
    
    vir_to_phy = {}
    for p, v in phy_to_vir.items():
        vir_to_phy.setdefault(v, []).append(p)

    # 计算总权重
    total_est = 0
    vir_edge_delays = []
    for i in range(len(vir_path)-1):
        u, v = vir_path[i], vir_path[i+1]
        d = G_vir[u][v].get('delay', 10)
        vir_edge_delays.append(d)
        total_est += d
    if total_est == 0: total_est = 1

    current_phy_src = src
    total_budget = 200

    for i in range(len(vir_path)):
        curr_domain = vir_path[i]
        domain_nodes = [n for n in vir_to_phy.get(curr_domain, []) if n in G_phy]
        
        print(f"\n   📍 域 [{curr_domain}] (含 {len(domain_nodes)} 节点)")
        
        if i < len(vir_path) - 1:
            next_domain = vir_path[i+1]
            # 找边界
            boundary = find_boundary_link(G_phy, domain_nodes, next_domain, phy_to_vir)
            if not boundary:
                print("      ❌ 边界中断！")
                break
            u_out, v_in, d = boundary
            
            # 预算
            budget = total_budget * (vir_edge_delays[i] / total_est)
            
            print(f"      - Ingress : {current_phy_src}")
            print(f"      - Egress  : {u_out} --> (Next: {v_in})")
            print(f"      - Budget  : {budget:.2f} ms")
            current_phy_src = v_in
        else:
            print(f"      - Ingress : {current_phy_src}")
            print(f"      - Dst     : {dst}")
            print(f"      - Budget  : 剩余全部")

def find_boundary_link(G, u_nodes, v_domain_id, phy_to_vir):
    best = None
    min_d = float('inf')
    for u in u_nodes:
        for v in G.neighbors(u):
            if phy_to_vir.get(v) == v_domain_id:
                d = G[u][v].get('delay', float('inf'))
                if d < min_d:
                    min_d = d
                    best = (u, v, d)
    return best

if __name__ == "__main__":
    test_geo_instruction_dispatch()