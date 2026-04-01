# -*- coding: utf-8 -*-
"""
File: src/traffic.py
Description: 业务流量生成器 (聚焦热点版: 极度收窄区域以引爆单点拥塞)
修正: 引入固定种子与排序，确保流量生成的确定性与包含关系 (消除锯齿)
"""
import random
import logging

class TrafficGenerator:
    def __init__(self, topology_manager):
        self.tm = topology_manager

    def _is_in_region(self, node_attrs, lat_range, lon_range):
        lat = node_attrs.get('lat')
        lon = node_attrs.get('lon')
        if lat is None or lon is None: return False
        
        # 经度归一化处理 (-180 ~ 180)
        if lon > 180: lon -= 360
        
        in_lat = lat_range[0] <= lat <= lat_range[1]
        in_lon = lon_range[0] <= lon <= lon_range[1]
        return in_lat and in_lon

    def generate_requests(self, G, num_requests=10):
        # [修改 1] 节点排序：确保每次运行的节点顺序绝对一致，防止随机性
        nodes = sorted(list(G.nodes(data=True)), key=lambda x: str(x[0]))
        
        # [修改 2] 固定随机种子：确保 Gen(50) 的前 30 个业务与 Gen(30) 完全一致
        # 这样不同负载下的业务就是“包含关系”而非“独立随机”，曲线会非常平滑
        random.seed(20260116) 
        
        # =========================================================================
        # [核心修改]: 极度收窄地理范围，制造"针尖"效应
        # 旧范围: 北美(20~60), 东亚(20~60) -> 范围太大，流量容易分散
        # 新范围: 仅限洛杉矶周边 -> 东京周边 (各 10度 x 10度)
        # =========================================================================
        
        # 源: 聚焦在美西海岸 (洛杉矶/旧金山附近)
        # 这将强迫所有流量都落入同一个 "虚拟LEO域"，争抢仅有的 1-2 个 MEO 出口
        SRC_LAT, SRC_LON = (30, 40), (-125, -115) 
        
        # 宿: 聚焦在东亚 (东京/上海附近)
        DST_LAT, DST_LON = (30, 40), (130, 145)   
        
        # 2. 筛选节点
        # 只选 LEO/Detect/Ground，因为它们是业务的发起者
        src_pool = [n for n, d in nodes if d.get('type') in ['LEO', 'Ground', 'Detect'] and self._is_in_region(d, SRC_LAT, SRC_LON)]
        dst_pool = [n for n, d in nodes if d.get('type') in ['LEO', 'Ground'] and self._is_in_region(d, DST_LAT, DST_LON)]
        
        # 3. 兜底机制：如果太窄导致选不到点，稍微扩大一点范围或回退到全网
        if len(src_pool) < 2 or len(dst_pool) < 2:
            # 扩充到半球级，防止报错
            print("   [Traffic] 热点区域节点不足，回退到宽域模式...")
            src_pool = [n for n, d in nodes if d.get('type') in ['LEO', 'Ground']]
            dst_pool = src_pool

        requests = []
        
        # [核心修改]: 提升走廊流量比例到 90%
        # 既然要测抗拥塞，就让压力来得更猛烈些
        corridor_count = int(num_requests * 0.9) 
        
        for _ in range(num_requests):
            if len(requests) < corridor_count:
                # 制造拥塞流量
                s = random.choice(src_pool)
                d = random.choice(dst_pool)
            else:
                # 制造背景噪声 (10%)
                all_nodes = [n for n, d in nodes if d.get('type') in ['LEO', 'Detect', 'Ground']]
                s = random.choice(all_nodes)
                d = random.choice(all_nodes)
                
            # 避免自环
            while s == d: 
                d = random.choice(dst_pool if len(requests) < corridor_count else all_nodes)
                
            req = {
                'src': s, 'dst': d,
                'bandwidth': 0, 'delay_req': 0, 'loss_req': 0 # 占位，由 simulation_utils 填充
            }
            requests.append(req)
            
        return requests
