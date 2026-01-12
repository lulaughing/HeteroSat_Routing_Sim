# -*- coding: utf-8 -*-
"""
File: test/check_ground_links.py
Description: 专门检查是否存在星地链路 (Ground/Facility Links)
"""
import sys
import os

# ==========================================
# [新增] 路径修复代码
# ==========================================
# 获取当前脚本所在目录 (test/)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录 (test/ 的上一级)
project_root = os.path.dirname(current_dir)
# 将根目录加入 Python 搜索路径
sys.path.append(project_root)
# ==========================================

from src.topology import TopologyManager
import networkx as nx

def check():
    print(f"🚀 正在加载拓扑缓存... (Root: {project_root})")
    tm = TopologyManager()
    
    # 获取 t=0 时刻的图
    print("📊 构建 t=0 时刻的拓扑图...")
    G = tm.get_graph_at_time(0)
    
    ground_links = []
    
    # 遍历所有边，寻找连接到 Ground 的边
    for u, v, data in G.edges(data=True):
        type_u = G.nodes[u]['type']
        type_v = G.nodes[v]['type']
        
        # 只要有一端是地面站
        if type_u == 'Ground' or type_v == 'Ground':
            ground_links.append((u, v, data))

    print(f"\n✅ 检查结果: t=0 时刻共有 {len(ground_links)} 条星地链路连接！")
    
    if ground_links:
        print("\n🔍 链路采样 (前 10 条):")
        print(f"{'Node A':<25} <--> {'Node B':<25} | {'Type':<15} | {'Distance':<10} | {'Delay':<10}")
        print("-" * 100)
        
        for i, (u, v, data) in enumerate(ground_links[:10]):
            # 确定哪端是卫星，哪端是地面
            type_u = G.nodes[u]['type']
            link_type = f"{type_u}<->{G.nodes[v]['type']}"
            print(f"{u:<25} <--> {v:<25} | {link_type:<15} | {data['distance']:.2f} km   | {data['delay']:.2f} ms")
    else:
        print("❌ 警告: 当前时刻没有发现星地链路。")
        print("   可能原因: t=0 时刻恰好所有卫星都还没飞过地面站上空。")
        print("   建议: 尝试修改 get_graph_at_time(300) 看看 5 分钟后的情况。")

if __name__ == "__main__":
    check()