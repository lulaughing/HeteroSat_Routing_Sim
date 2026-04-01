# -*- coding: utf-8 -*-
"""
File: src/topology.py
Description: 拓扑管理器 (集成 Link Model + 异构带宽配置 + 日志修复)
"""
import networkx as nx
import pandas as pd
import os
import pickle
import logging
import math
import re
from collections import defaultdict
from src.data_loader import STKDataLoader
from src.link_model import apply_traffic_physics  # [引入物理模型]
from config.settings import DATA_DIRS, CACHE_DIR, LINK_RANGE_LIMITS
# [修改 1] 引入项目统一的日志工具
from src.utils import get_logger 

class TopologyManager:
    def __init__(self):
        self.data_loader = STKDataLoader()
        self.ephemeris_data = {} 
        self.access_data = {}    
        self.stable_link_whitelist = set() 
        self.cache_path = os.path.join(CACHE_DIR, 'topology_cache_v5_dedup.pkl')
        
        # [修改 2] 正确初始化日志，修复 TypeError 报错
        self.logger = get_logger('TOPO', 'topology.log')
        
        self._load_data()

    def _load_data(self):
        if os.path.exists(self.cache_path):
            self.logger.info(">> [Cache] 发现缓存文件，正在读取...")
            with open(self.cache_path, 'rb') as f:
                cache = pickle.load(f)
                self.ephemeris_data = cache['ephemeris']
                self.access_data = cache['access']
                self.stable_link_whitelist = cache.get('whitelist', set())
            if not self.stable_link_whitelist: self._compute_stable_topology()
            self.logger.info(">> [Topology] 成功从缓存加载数据！")
        else:
            self.logger.info(">> [Topology] 未发现缓存，开始解析原始 STK 数据...")
            self._parse_raw_files()
            self._compute_stable_topology()
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(self.cache_path, 'wb') as f:
                pickle.dump({'ephemeris': self.ephemeris_data, 'access': self.access_data, 'whitelist': self.stable_link_whitelist}, f)
            self.logger.info(">> [Cache] 缓存保存完成！")

    def _parse_raw_files(self):
        print(f"   [1/3] 正在加载星历数据...")
        for root, _, files in os.walk(DATA_DIRS['ephemeris']):
            for file in files:
                if file.endswith('.txt'):
                    node_name = os.path.splitext(file)[0]
                    file_path = os.path.join(root, file)
                    df = self.data_loader.load_ephemeris(file_path)
                    if df is not None:
                        df.attrs['type'] = self._get_node_type(node_name)
                        self.ephemeris_data[node_name] = df
        
        print(f"   [2/3] 正在加载 Access 数据...")
        access_files = [f for f in os.listdir(DATA_DIRS['access']) if f.endswith('.txt')]
        for file in access_files:
            path = os.path.join(DATA_DIRS['access'], file)
            self.access_data.update(self.data_loader.load_stk_report(path, report_type='Access'))

    def _get_node_type(self, name):
        if 'Detect' in name: return 'Detect'
        if 'LEO' in name: return 'LEO'
        if 'MEO' in name: return 'MEO'
        if 'GEO' in name: return 'GEO'
        if 'Facility' in name or 'Ground' in name: return 'Ground'
        return 'Unknown'

    def _extract_plane_id(self, node_name):
        digits = re.findall(r'\d+', node_name)
        if not digits: return None
        num_str = "".join(digits)
        if len(num_str) >= 4: return num_str[:2]
        return None

    def _compute_stable_topology(self):
        print(">> [Topology] 正在计算稳定拓扑 (去重 + 强制结构化)...")
        valid_candidates = defaultdict(list) 
        for (u, v), df in self.access_data.items():
            if u not in self.ephemeris_data or v not in self.ephemeris_data: continue
            type_u = self.ephemeris_data[u].attrs['type']
            type_v = self.ephemeris_data[v].attrs['type']
            max_dist = self._get_max_distance(u, v, type_u, type_v)
            sample_time = df.iloc[0]['StartTime']
            dist = self._get_distance_at_time(u, v, sample_time)
            if dist > max_dist: continue
            total_dur = (df['StopTime'] - df['StartTime']).sum()
            valid_candidates[u].append((v, total_dur, dist))
            valid_candidates[v].append((u, total_dur, dist))

        self.stable_link_whitelist = set()
        for node, neighbors in valid_candidates.items():
            unique_neighbors_map = {}
            for n, dur, dist in neighbors: unique_neighbors_map[n] = (n, dur, dist)
            unique_neighbors = list(unique_neighbors_map.values())
            type_node = self.ephemeris_data[node].attrs['type']
            if type_node in ['LEO', 'Detect']:
                my_plane = self._extract_plane_id(node)
                same_plane = []
                inter_plane = []
                others = []
                for n, dur, dist in unique_neighbors:
                    n_type = 'Unknown'
                    if n in self.ephemeris_data: n_type = self.ephemeris_data[n].attrs['type']
                    if n_type == type_node:
                        n_plane = self._extract_plane_id(n)
                        if my_plane and n_plane and my_plane == n_plane: same_plane.append((n, dur, dist))
                        else: inter_plane.append((n, dur, dist))
                    else: others.append((n, dur, dist))
                same_plane.sort(key=lambda x: (-x[1], x[2]))
                inter_plane.sort(key=lambda x: (-x[1], x[2]))
                for n, _, _ in same_plane[:2]: self.stable_link_whitelist.add(tuple(sorted((node, n))))
                for n, _, _ in inter_plane[:2]: self.stable_link_whitelist.add(tuple(sorted((node, n))))
                for n, _, _ in others: self.stable_link_whitelist.add(tuple(sorted((node, n))))
            else:
                for n, _, _ in unique_neighbors: self.stable_link_whitelist.add(tuple(sorted((node, n))))
        print(f"   - 拓扑清洗完成，保留了 {len(self.stable_link_whitelist)} 条稳定链路。")

    def _get_max_distance(self, name_u, name_v, type_u, type_v):
        key = tuple(sorted((type_u, type_v)))
        return LINK_RANGE_LIMITS.get(key, 10000.0)

    def _get_distance_at_time(self, u, v, t):
        df_u = self.ephemeris_data[u]
        df_v = self.ephemeris_data[v]
        idx_u = min(df_u['SimTime'].searchsorted(t), len(df_u)-1)
        idx_v = min(df_v['SimTime'].searchsorted(t), len(df_v)-1)
        return self._calculate_distance(
            df_u.iloc[idx_u]['Lat'], df_u.iloc[idx_u]['Lon'], df_u.iloc[idx_u]['Alt'],
            df_v.iloc[idx_v]['Lat'], df_v.iloc[idx_v]['Lon'], df_v.iloc[idx_v]['Alt']
        )

    def _calculate_distance(self, lat1, lon1, alt1, lat2, lon2, alt2):
        R = 6371.0
        to_rad = math.pi / 180.0
        x1 = (R+alt1) * math.cos(lat1*to_rad) * math.cos(lon1*to_rad)
        y1 = (R+alt1) * math.cos(lat1*to_rad) * math.sin(lon1*to_rad)
        z1 = (R+alt1) * math.sin(lat1*to_rad)
        x2 = (R+alt2) * math.cos(lat2*to_rad) * math.cos(lon2*to_rad)
        y2 = (R+alt2) * math.cos(lat2*to_rad) * math.sin(lon2*to_rad)
        z2 = (R+alt2) * math.sin(lat2*to_rad)
        return ((x1-x2)**2 + (y1-y2)**2 + (z1-z2)**2)**0.5

    def _get_link_capacity(self, u, v):
        """
        [修正版] 四层架构异构带宽配置
        GEO / MEO / LEO / Detect
        """
        # 1. 获取节点类型
        # 假设 ephemeris_data 已正确加载 type 属性
        type_u = self.ephemeris_data[u].attrs.get('type', 'Unknown')
        type_v = self.ephemeris_data[v].attrs.get('type', 'Unknown')
        
        types = {type_u, type_v}
        
        # =========================================================
        # 第一层级：星地回传 (Ground Segment)
        # =========================================================
        # 地面站接收能力极强，不应成为瓶颈
        if 'Ground' in types:
            return 100 # Mbps
            
        # =========================================================
        # 第二层级：高轨骨干 (GEO/MEO Backbone)
        # =========================================================
        # MEO-MEO, GEO-GEO, MEO-GEO
        # 这是核心骨干网，带宽极大
        if ('MEO' in types or 'GEO' in types) and not ('LEO' in types or 'Detect' in types):
            return 100 # Mbps (足够容纳 6条并发遥感流)
            
        # =========================================================
        # 第三层级：跨层接入 (Cross-Layer Access) - 关键瓶颈
        # =========================================================
        # LEO -> MEO, Detect -> MEO
        # 或者是 GEO 接入 (如果有)
        # 这里是 H-IGA 发挥优势的地方：寻找空闲的接入时隙
        if ('MEO' in types or 'GEO' in types) and ('LEO' in types or 'Detect' in types):
            return 60 # Mbps (能容纳 3条并发遥感流，第4条就会堵)
            
        # =========================================================
        # 第四层级：低轨 & 探测层互联 (Low Orbit & Sensing Layer)
        # =========================================================
        
        # 4.1 Detect -> LEO (层间汇报)
        # 如果 Detect 没法直连 MEO，它会试图传给 LEO
        # [优化] 提升到 50Mbps 以支持 Remote Sensing (35Mbps)
        if 'Detect' in types and 'LEO' in types:
            return 50 # Mbps (原 30Mbps 会导致 35M 业务必丢包)
            
        # 4.2 Detect -> Detect (同层 ISL)
        # 探测卫星间协作能力弱 -> [优化] 提升到 50Mbps
        if type_u == 'Detect' and type_v == 'Detect':
            return 50 # Mbps
            
        # 4.3 LEO -> LEO (同层 ISL)
        # 标准 LEO 星间链路 -> [优化] 提升到 50Mbps
        if type_u == 'LEO' and type_v == 'LEO':
            return 50 # Mbps

        # 默认兜底
        return 10

    def get_graph_at_time(self, time_step):
        G = nx.Graph()
        for name, df in self.ephemeris_data.items():
            idx = min(df['SimTime'].searchsorted(time_step), len(df)-1)
            row = df.iloc[idx]
            G.add_node(name, type=df.attrs.get('type', 'Unknown'), lat=row['Lat'], lon=row['Lon'], alt=row['Alt'])
        
        for (u, v), df in self.access_data.items():
            if tuple(sorted((u, v))) not in self.stable_link_whitelist: continue
            valid = df[(df['StartTime'] <= time_step) & (df['StopTime'] >= time_step)]
            if not valid.empty:
                if u in G.nodes and v in G.nodes:
                    dist = self._get_distance_at_time(u, v, time_step)
                    
                    # [关键修改] 调用 _get_link_capacity 获取动态带宽
                    cap = self._get_link_capacity(u, v)
                    
                    G.add_edge(u, v, 
                               distance=dist, 
                               delay=dist/299.79, 
                               static_delay=dist/299.79, 
                               capacity=cap, 
                               loss=0.001,
                               used_bw=0)
        return G

    def update_link_state(self, G, u, v, bw):
        """
        更新链路状态 (代理到 link_model，执行拥塞计算)
        """
        apply_traffic_physics(G, u, v, bw)
