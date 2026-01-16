
import os
import sys
import numpy as np
import networkx as nx
from collections import defaultdict

# 添加项目根目录到路径
sys.path.append(os.getcwd())

from src.topology import TopologyManager

def inspect_topology_stats():
    print("正在初始化 TopologyManager...")
    tm = TopologyManager()
    
    # 采样几个时间点，因为距离随时间变化
    time_steps = [0, 100, 200]
    
    stats = defaultdict(lambda: {'bw': [], 'dist': [], 'loss': []})
    
    print(f"开始采样时间点: {time_steps}")
    
    for t in time_steps:
        print(f"  分析 T={t} 的拓扑...")
        G = tm.get_graph_at_time(t)
        
        for u, v, d in G.edges(data=True):
            # 识别链路类型
            type_u = G.nodes[u]['type']
            type_v = G.nodes[v]['type']
            link_type = tuple(sorted([type_u, type_v]))
            
            # 记录数据
            stats[link_type]['bw'].append(d['capacity'])
            stats[link_type]['dist'].append(d['distance'])
            stats[link_type]['loss'].append(d['loss'])

    print("\n" + "="*80)
    print(f"{'Link Type':<30} | {'Bandwidth (Mbps)':<20} | {'Delay (ms) [Dist/c]':<25} | {'Base Loss':<10}")
    print("-" * 80)
    
    for link_type, data in stats.items():
        type_str = f"{link_type[0]} <-> {link_type[1]}"
        
        # 带宽
        min_bw = min(data['bw'])
        max_bw = max(data['bw'])
        bw_str = f"{min_bw}" if min_bw == max_bw else f"{min_bw}-{max_bw}"
        
        # 时延 (距离 km / 299.79 km/ms)
        min_dist = min(data['dist'])
        max_dist = max(data['dist'])
        min_delay = min_dist / 299.79
        max_delay = max_dist / 299.79
        delay_str = f"{min_delay:.2f} ~ {max_delay:.2f}"
        
        # 丢包
        min_loss = min(data['loss'])
        loss_str = f"{min_loss:.1%}"
        
        print(f"{type_str:<30} | {bw_str:<20} | {delay_str:<25} | {loss_str:<10}")
    
    print("="*80)

if __name__ == "__main__":
    inspect_topology_stats()
