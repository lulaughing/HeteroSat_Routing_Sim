# -*- coding: utf-8 -*-
"""
File: debug_data_status.py
Description: 数据状态诊断工具
"""
import pandas as pd
import networkx as nx
from src.topology import TopologyManager

def check_status():
    print("🔍 [诊断] 正在读取拓扑缓存...")
    tm = TopologyManager() # 这会读取 pkl
    
    # 1. 检查时间范围
    print("\n---------- 1. 时间范围检查 ----------")
    if not tm.ephemeris_cache:
        print("❌ 严重错误: 星历缓存为空！")
        return

    # 随便取一颗卫星看看它的时间轴
    sample_sat = list(tm.ephemeris_cache.keys())[0]
    df = tm.ephemeris_cache[sample_sat]
    t_min = df['SimTime'].min()
    t_max = df['SimTime'].max()
    
    print(f"采样卫星: {sample_sat}")
    print(f"数据时间覆盖: {t_min:.1f}s 到 {t_max:.1f}s")
    print(f"当前仿真设定: 0s 到 30s")
    
    if t_min > 0:
        print(f"⚠️ 警告: 数据起始时间 ({t_min}) 大于 0！仿真器在 t=0 时读不到数据！")
        print(f"   -> 建议修改 config/settings.py 或 main.py，将起始时间设置为 {int(t_min)}")

    # 2. 检查节点类型
    print("\n---------- 2. 节点类型检查 (t = StartTime) ----------")
    # 构建起始时刻的图
    start_time = max(0, t_min) 
    G = tm.get_graph_at_time(start_time)
    
    print(f"构建了 t={start_time} 的拓扑图")
    print(f"节点总数: {G.number_of_nodes()}")
    
    # 统计类型
    node_types = {}
    ground_names = []
    
    for n, d in G.nodes(data=True):
        t = d.get('type', 'None')
        node_types[t] = node_types.get(t, 0) + 1
        if t == 'Ground':
            ground_names.append(n)
        if 'Facility' in str(n) and t != 'Ground':
            print(f"⚠️ 发现命名含 Facility 但类型不是 Ground 的节点: {n} (Type: {t})")

    print(f"节点类型分布: {node_types}")
    
    if 'Ground' not in node_types and 'Facility' not in str(node_types):
        print("❌ 致命错误: 图中没有地面站 (Ground)！业务无法生成。")
        print("   -> 请检查 src/topology.py 中的 get_sat_type 函数")
        
    if 'Detect' not in node_types and 'LEO' not in node_types:
        print("❌ 致命错误: 图中没有探测卫星 (Detect/LEO)！业务无法生成。")

    # 3. 模拟业务生成逻辑
    print("\n---------- 3. 模拟业务生成测试 ----------")
    nodes = list(G.nodes(data=True))
    # 复制 traffic.py 的逻辑
    detect_nodes = [n for n, d in nodes if d['type'] in ['Detect', 'LEO']]
    ground_nodes = [n for n, d in nodes if d['type'] == 'Ground' or 'Facility' in str(n)]
    
    print(f"TrafficGenerator 能看到的源节点数: {len(detect_nodes)}")
    print(f"TrafficGenerator 能看到的宿节点数: {len(ground_nodes)}")
    
    if len(detect_nodes) > 0 and len(ground_nodes) > 0:
        print("✅ 诊断结论: 当前时间点具备生成业务的条件。")
    else:
        print("❌ 诊断结论: 条件不满足，无法生成业务。")

if __name__ == "__main__":
    check_status()