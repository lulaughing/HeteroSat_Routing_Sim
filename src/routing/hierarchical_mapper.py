# -*- coding: utf-8 -*-
"""
File: src/routing/hierarchical_mapper.py
Description: 虚拟拓扑管理器 (最终修正版 - 地面站接入归属 + 属性对齐)
"""
import networkx as nx
import logging
import re

logger = logging.getLogger(__name__)

# [论文参数] 区域划分粒度
GRID_LAT_STEP = 45.0  # 纬度步长
GRID_LON_STEP = 60.0  # 经度步长

class VirtualTopologyManager:
    def __init__(self):
        pass

    def _calculate_sat_domain(self, node_name, attrs):
        """
        计算卫星节点的地理栅格域 ID
        """
        if 'GEO' in node_name or 'MEO' in node_name:
            return node_name
            
        lat = attrs.get('lat')
        lon = attrs.get('lon')
        
        if lat is None or lon is None:
            return "Domain_Unknown"
            
        # 计算网格索引
        lat_idx = int((lat + 90) / GRID_LAT_STEP)
        lat_idx = min(lat_idx, int(180 / GRID_LAT_STEP) - 1)
        
        lon_idx = int((lon + 180) / GRID_LON_STEP)
        lon_idx = min(lon_idx, int(360 / GRID_LON_STEP) - 1)
        
        prefix = "LEO" if "LEO" in node_name else "Detect"
        return f"Virtual_{prefix}_Lat{lat_idx}_Lon{lon_idx}"

    def build_virtual_graph(self, G_phy):
        """
        构建全局混合时变图 G(t)
        """
        G_vir = nx.Graph()
        phy_to_vir = {} 
        vir_to_phy = {} 
        
        # --- 1. 卫星节点映射 ---
        for node, data in G_phy.nodes(data=True):
            if 'Facility' in node or 'Ground' in node:
                continue
                
            v_id = self._calculate_sat_domain(node, data)
            phy_to_vir[node] = v_id
            
            if v_id not in vir_to_phy: vir_to_phy[v_id] = []
            vir_to_phy[v_id].append(node)
            
            if v_id not in G_vir:
                G_vir.add_node(v_id, type='Virtual_Domain')

        # --- 2. 地面站接入归属 (仅更新映射，不作为路由节点) ---
        for node, data in G_phy.nodes(data=True):
            if 'Facility' in node or 'Ground' in node:
                neighbors = list(G_phy.neighbors(node))
                access_sat = None
                for n in neighbors:
                    if n in phy_to_vir:
                        access_sat = n
                        break
                
                if access_sat:
                    v_id = phy_to_vir[access_sat]
                    phy_to_vir[node] = v_id # 继承接入域ID
                    vir_to_phy[v_id].append(node)

        # --- 3. 物理链路聚合 ---
        inter_domain_links = {}
        for u, v, data in G_phy.edges(data=True):
            dom_u = phy_to_vir.get(u)
            dom_v = phy_to_vir.get(v)
            
            # 只有两个不同的域之间才会有虚边
            # 地面站和它的接入卫星在同一个域，所以不会产生虚边 (正确)
            if dom_u and dom_v and dom_u != dom_v:
                link_key = tuple(sorted((dom_u, dom_v)))
                if link_key not in inter_domain_links:
                    inter_domain_links[link_key] = []
                inter_domain_links[link_key].append(data)

        # --- 4. 计算虚边权重 ---
        count_virtual = 0
        for (dom_a, dom_b), links in inter_domain_links.items():
            if not links: continue 
            
            agg_cap = min([l.get('capacity', 0) for l in links])
            agg_delay = sum([l.get('delay', 10) for l in links]) / len(links)
            agg_loss = max([l.get('loss', 0) for l in links])
            link_count = len(links)
            
            G_vir.add_edge(dom_a, dom_b, 
                           capacity=agg_cap,      
                           bandwidth=agg_cap,     
                           delay=agg_delay,
                           loss=agg_loss,
                           link_count=link_count)
            count_virtual += 1

        logger.info(f"   🌐 [VTM] 虚拟拓扑构建完成: {len(G_vir.nodes)} 节点, {count_virtual} 虚边")
        return G_vir, phy_to_vir