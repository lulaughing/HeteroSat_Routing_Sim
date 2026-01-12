# -*- coding: utf-8 -*-
"""
File: test/test_topology_cleaning.py
Description: 拓扑清洗逻辑深度诊断 (通用版: 支持 Detect0101)
"""
import sys
import os
import re

# 路径 Hack
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from src.topology import TopologyManager
from config.settings import CACHE_DIR

def diagnose_target(target_name):
    print(f"🕵️‍♂️ [Diagnosis] 启动 {target_name} 邻居选拔侦探程序...")

    # 1. 强力清除缓存
    if os.path.exists(CACHE_DIR):
        for f in os.listdir(CACHE_DIR):
            if f.endswith(".pkl") and "topology" in f:
                try:
                    os.remove(os.path.join(CACHE_DIR, f))
                except: pass

    # 2. 初始化
    print("   ⏳ 正在重新计算拓扑 (含去重 + 结构化)...")
    tm = TopologyManager()
    
    if target_name not in tm.ephemeris_data:
        print(f"❌ 错误: 找不到 {target_name} 的星历数据")
        return

    # 3. 现场还原
    print(f"\n📊 {target_name} 的选拔赛现场还原:")
    target_plane = tm._extract_plane_id(target_name)
    target_type = tm.ephemeris_data[target_name].attrs['type']
    print(f"   - 目标身份: {target_name} (类型: {target_type}, 轨道面: {target_plane})")
    
    # 收集并去重
    neighbors_map = {}
    
    for (u, v), df in tm.access_data.items():
        neighbor = None
        if u == target_name: neighbor = v
        elif v == target_name: neighbor = u
        
        if neighbor:
            # 只看同类型的邻居 (Detect连Detect)
            if neighbor not in tm.ephemeris_data: continue
            n_type = tm.ephemeris_data[neighbor].attrs['type']
            if n_type != target_type: continue

            # 计算距离 (t=0)
            t0 = df.iloc[0]['StartTime']
            dist = tm._get_distance_at_time(target_name, neighbor, t0)
            duration = (df['StopTime'] - df['StartTime']).sum()
            n_plane = tm._extract_plane_id(neighbor)
            
            # 存入字典去重
            neighbors_map[neighbor] = {
                'name': neighbor,
                'plane': n_plane,
                'dist': dist,
                'dur': duration
            }

    unique_neighbors = list(neighbors_map.values())

    # 4. 分组展示
    same_plane_group = []
    inter_plane_group = []
    
    for n in unique_neighbors:
        if n['plane'] == target_plane:
            same_plane_group.append(n)
        else:
            inter_plane_group.append(n)
            
    # 排序
    same_plane_group.sort(key=lambda x: (-x['dur'], x['dist']))
    inter_plane_group.sort(key=lambda x: (-x['dur'], x['dist']))

    # --- 打印同轨 ---
    print(f"\n   🔵 [同轨赛道] (Plane {target_plane}) - 目标录取 2 名:")
    for i, n in enumerate(same_plane_group):
        status = "✅ 晋级" if i < 2 else "❌ 淘汰"
        print(f"      {i+1}. {n['name']} | 距离: {n['dist']:.0f} km | {status}")

    # --- 打印异轨 ---
    print(f"\n   🟠 [异轨赛道] (Other Planes) - 目标录取 2 名:")
    for i, n in enumerate(inter_plane_group):
        # 重点关注对象
        is_highlight = n['name'] in ['Detect1001', 'Detect0210', 'Detect0201']
        prefix = "👉" if is_highlight else "  "
        
        status = "✅ 晋级" if i < 2 else "❌ 淘汰"
        print(f"   {prefix} {i+1}. {n['name']} (Plane {n['plane']}) | 距离: {n['dist']:.0f} km | {status}")
        
        if i >= 7: 
            print("      ... (其余省略)")
            break

    # 5. 最终核对
    print(f"\n📜 [最终核查] Whitelist 中的实际结果:")
    whitelist_neighbors = []
    for (u, v) in tm.stable_link_whitelist:
        if u == target_name: whitelist_neighbors.append(v)
        elif v == target_name: whitelist_neighbors.append(u)
    
    final_list = sorted([n for n in whitelist_neighbors if target_type in n])
    print(f"   -> {final_list}")
    
    # Detect0101 的预期邻居 (根据 STK 截图推断)
    # 同轨: 0102, 0110
    # 异轨: 0210 (近), 1001 (近, 闭环)
    expected = {'Detect0102', 'Detect0110', 'Detect0210', 'Detect1001'}
    
    # 检查交集
    matched = set(final_list) & expected
    if matched == expected:
        print("\n🎉 完美！Detect0101 的邻居符合 STK 物理事实。")
    else:
        print(f"\n⚠️ 结果差异:")
        print(f"   期望: {expected}")
        print(f"   实际: {set(final_list)}")

if __name__ == "__main__":
    diagnose_target("Detect0101")