# -*- coding: utf-8 -*-
"""
File: test/debug_topology.py
Description: 调试拓扑构建模块 (解决路径引用问题)
"""
import sys
import os

# ==========================================
# [关键] 将项目根目录添加到 Python 搜索路径
# ==========================================
# 获取当前脚本所在目录 (F:\HeteroSat_Routing_Sim\test)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录 (F:\HeteroSat_Routing_Sim)
project_root = os.path.dirname(current_dir)
# 加入系统路径
sys.path.append(project_root)
# ==========================================

from src.topology import TopologyManager
from config.settings import SIM_START_TIME

def debug_topo_build():
    print(f"🚀 [Debug] 启动拓扑调试，根目录: {project_root}")
    
    # 1. 初始化管理器 (这会加载所有数据，可能需要几秒钟)
    tm = TopologyManager()
    
    # 2. 选择一个仿真时刻 (例如第 0 秒)
    # 也可以选大一点，比如 3600 秒，看卫星动了没
    test_time = 0.0 
    
    print(f"\n📊 [Debug] 正在构建 t={test_time}s 的全网拓扑...")
    G = tm.get_graph_at_time(test_time)
    
    # 3. 打印统计信息
    num_nodes = G.number_of_nodes()
    num_edges = G.number_of_edges()
    
    print(f"✅ 拓扑构建完成!")
    print(f"   - 节点总数: {num_nodes}")
    print(f"   - 链路总数: {num_edges}")
    
    # 4. 节点采样检查
    print("\n🔍 [节点采样] 前 3 个节点:")
    for i, node in enumerate(list(G.nodes(data=True))[:3]):
        n_id, data = node
        print(f"   {i+1}. {n_id} ({data.get('type')}): Lat={data.get('lat'):.2f}, Lon={data.get('lon'):.2f}, Alt={data.get('alt'):.2f}")

    # 5. 链路采样检查
    print("\n🔗 [链路采样] 前 5 条链路:")
    if num_edges > 0:
        for i, edge in enumerate(list(G.edges(data=True))[:5]):
            u, v, data = edge
            print(f"   {i+1}. {u} <--> {v}")
            print(f"      距离: {data['distance']:.2f} km")
            print(f"      时延: {data['delay']:.2f} ms")
    else:
        print("   ⚠️ 警告: 当前时刻图中没有边！可能原因：")
        print("      1. 时间 t=0 时没有可见性链路 (尝试改 test_time)")
        print("      2. Access/AER 数据未正确匹配")
        print("      3. 距离约束过严被过滤")

if __name__ == "__main__":
    debug_topo_build()