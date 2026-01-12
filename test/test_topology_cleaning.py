# -*- coding: utf-8 -*-
"""
File: test/test_topology_cleaning.py
Description: 拓扑清洗逻辑深度诊断 (LEO0101 专案组)
"""
import sys
import os
import shutil
import re

# 路径 Hack
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from src.topology import TopologyManager
from config.settings import CACHE_DIR

def diagnose_leo0101():
    print("🕵️‍♂️ [Diagnosis] 启动 LEO0101 邻居选拔侦探程序...")

    # 1. 强力清除缓存 (确保逻辑从零开始跑)
    # ----------------------------------------------------
    # 删除目录下所有 pkl 文件，防止版本号混淆
    if os.path.exists(CACHE_DIR):
        for f in os.listdir(CACHE_DIR):
            if f.endswith(".pkl") and "topology" in f:
                os.remove(os.path.join(CACHE_DIR, f))
                print(f"   🗑️ 已删除旧缓存: {f}")

    # 2. 初始化 (触发计算)
    # ----------------------------------------------------
    print("   ⏳ 正在重新计算拓扑 (请稍候)...")
    tm = TopologyManager()
    
    target = "LEO0101"
    if target not in tm.ephemeris_data:
        print(f"❌ 错误: 找不到 {target} 的星历数据")
        return

    # 3. 模拟 TopologyManager 内部的分类逻辑
    # ----------------------------------------------------
    print(f"\n📊 {target} 的选拔赛现场还原:")
    
    # 获取 target 的轨道面
    target_plane = tm._extract_plane_id(target)
    print(f"   - 目标身份: {target} (轨道面: {target_plane})")
    
    # 收集所有原始邻居
    raw_neighbors = []
    for (u, v), df in tm.access_data.items():
        neighbor = None
        if u == target: neighbor = v
        elif v == target: neighbor = u
        
        if neighbor and ("LEO" in neighbor): # 只看 LEO 邻居
            # 计算距离 (取 t=0)
            t0 = df.iloc[0]['StartTime']
            dist = tm._get_distance_at_time(target, neighbor, t0)
            duration = (df['StopTime'] - df['StartTime']).sum()
            
            # 解析邻居轨道面
            n_plane = tm._extract_plane_id(neighbor)
            
            raw_neighbors.append({
                'name': neighbor,
                'plane': n_plane,
                'dist': dist,
                'dur': duration
            })

    # 4. 分组展示
    # ----------------------------------------------------
    same_plane_group = []
    inter_plane_group = []
    
    for n in raw_neighbors:
        if n['plane'] == target_plane:
            same_plane_group.append(n)
        else:
            inter_plane_group.append(n)
            
    # 排序 (时长降序 -> 距离升序)
    same_plane_group.sort(key=lambda x: (-x['dur'], x['dist']))
    inter_plane_group.sort(key=lambda x: (-x['dur'], x['dist']))

    # --- 打印同轨组 ---
    print(f"\n   🔵 [同轨赛道] (Plane {target_plane}) - 目标录取 2 名:")
    for i, n in enumerate(same_plane_group):
        status = "✅ 晋级" if i < 2 else "❌ 淘汰"
        print(f"      {i+1}. {n['name']} | 距离: {n['dist']:.0f} km | {status}")

    # --- 打印异轨组 ---
    print(f"\n   🟠 [异轨赛道] (Other Planes) - 目标录取 2 名:")
    for i, n in enumerate(inter_plane_group):
        # 重点关注 LEO1515 和 LEO0201
        is_highlight = n['name'] in ['LEO1515', 'LEO0201']
        prefix = "👉" if is_highlight else "  "
        
        status = "✅ 晋级" if i < 2 else "❌ 淘汰"
        print(f"   {prefix} {i+1}. {n['name']} (Plane {n['plane']}) | 距离: {n['dist']:.0f} km | {status}")
        
        # 只打印前 8 名，后面太长不看
        if i >= 7: 
            print("      ... (其余省略)")
            break

    # 5. 最终核对白名单
    # ----------------------------------------------------
    print(f"\n📜 [最终核查] Whitelist 中的实际结果:")
    whitelist_neighbors = []
    for (u, v) in tm.stable_link_whitelist:
        if u == target: whitelist_neighbors.append(v)
        elif v == target: whitelist_neighbors.append(u)
    
    # 过滤出 LEO
    leo_final = sorted([n for n in whitelist_neighbors if "LEO" in n])
    print(f"   -> {leo_final}")
    
    expected = {'LEO0102', 'LEO0115', 'LEO0201', 'LEO1515'}
    missing = expected - set(leo_final)
    
    if not missing:
        print("\n🎉 完美！所有预期的 Walker 邻居都存在。")
    else:
        print(f"\n⚠️ 警告！缺失邻居: {missing}")
        print("   请检查上方列表，看看是谁把它们挤下去了。")

if __name__ == "__main__":
    diagnose_leo0101()