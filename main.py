# -*- coding: utf-8 -*-
"""
File: main.py
Description: 异构星座路由仿真 (物理法则公平对比版 - 黄金参数调优)
"""
import copy
import pandas as pd
import numpy as np
import networkx as nx
import random
import os
import json
import logging
from tqdm import tqdm
from datetime import datetime 

from src.utils import get_flow_logger, get_net_logger, SESSION_DIR
from src.topology import TopologyManager
from src.traffic import TrafficGenerator
from src.routing.dijkstra import DijkstraStrategy
from src.routing.iga.iga import IGAStrategy
from src.routing.hierarchical_mapper import VirtualTopologyManager
from src.routing.inter_algo import InterDomainAlgorithm
from config.settings import RESULTS_DIR

from src.simulation_utils import (
    manage_traffic, 
    log_network_snapshot, 
    decompose_and_execute_hierarchical,
    get_sim_config,
    ensure_dir
)
from src.routing.sga import SGAStrategy

# 获取日志句柄
flog = get_flow_logger()
nlog = get_net_logger()

# ==========================================
# [配置] 仿真参数 (从工具类获取全局配置)
# ==========================================
cfg = get_sim_config()
SIM_START = cfg['SIM_START']
SIM_DURATION = cfg['SIM_DURATION']
TIME_STEP = cfg['TIME_STEP']
REQUESTS_PER_STEP = cfg['REQUESTS_PER_STEP']

USE_EXISTING_TRAFFIC = True 
TRAFFIC_DATA_DIR = os.path.join("data", "traffic_cache_main")
ROUTING_INFO_DIR = os.path.join(SESSION_DIR, 'routing_info')

SERVICE_TYPES = {
    # 1. 语音: 极小流，时延敏感。
    # 带宽 1Mbps，占 20M LEO 链路的 5%，容易存活。
    'Voice_Critical':   {'bandwidth': 1,   'delay_req': 180,  'loss_req': 0.001, 'priority': 0.8},
    
    # 2. 遥感: 【核心参数】45 Mbps。
    # 逻辑: 
    # - 45M > 20M (LEO同/异轨): Dijkstra 走底层必堵 (Util > 200%)。
    # - 45M < 100M (MEO接入): H-IGA 只要跳到 MEO 层，带宽充足，成功率极高。
    'Remote_Sensing':   {'bandwidth': 45,  'delay_req': 2000, 'loss_req': 0.01,  'priority': 0.3},
    
    # 3. 尽力而为: 5Mbps。
    # 用于填充网络背景流量。
    'Best_Effort':      {'bandwidth': 5,   'delay_req': 800,  'loss_req': 0.05,  'priority': 0.5}
}

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def manage_traffic(traffic_gen, G, time_step, count):
    ensure_dir(TRAFFIC_DATA_DIR)
    filename = f"requests_T{time_step}_N{count}.json"
    filepath = os.path.join(TRAFFIC_DATA_DIR, filename)
    
    if USE_EXISTING_TRAFFIC and os.path.exists(filepath):
        flog.info(f"   📂 加载历史流量: {filename}")
        with open(filepath, 'r') as f:
            raw_reqs = json.load(f)
        return raw_reqs
    else:
        flog.info(f"   🎲 生成新流量并保存: {filename}")
        raw_reqs = traffic_gen.generate_requests(G, num_requests=count)
        types = list(SERVICE_TYPES.keys())
        for i, req in enumerate(raw_reqs):
            s_type = random.choice(types)
            req.update(SERVICE_TYPES[s_type])
            req['service_type'] = s_type
            req['id'] = i
        with open(filepath, 'w') as f:
            json.dump(raw_reqs, f, indent=2)
        return raw_reqs

def log_network_snapshot(G, time_step, algo_name):
    nlog.info(f"--- [Net-State T={time_step}] Algo: {algo_name} ---")
    busy_links = []
    total_used = 0
    for u, v, d in G.edges(data=True):
        used = d.get('used_bw', 0)
        cap = d.get('capacity', 200) 
        total_used += used
        if used > 0:
            util = used / cap if cap > 0 else 0
            busy_links.append((u, v, used, cap, util))
    busy_links.sort(key=lambda x: x[4], reverse=True)
    nlog.info(f"   📊 总流量: {total_used:.1f} Mbps | 活跃链路: {len(busy_links)}")
    if busy_links:
        nlog.info(f"   🔥 {algo_name} 最拥塞链路 Top 5:")
        for i, (u, v, used, cap, util) in enumerate(busy_links[:5]):
            nlog.info(f"      {i+1}. {u}<->{v}: {util*100:.1f}% ({used:.0f}/{cap})")
    nlog.info("")


def decompose_and_execute_hierarchical(G_phy, G_vir, vir_path, phy_to_vir, src, dst, qos, algo_intra, topo_mgr):
    vir_to_phy = {}
    for p, v in phy_to_vir.items(): vir_to_phy.setdefault(v, []).append(p)
    full_path = []
    log = [] 
    
    total_est = sum([G_vir[vir_path[i]][vir_path[i+1]].get('delay', 10) for i in range(len(vir_path)-1)]) or 1
    
    msg_head = f"[Global] Req: {src}->{dst} ({qos['service_type']}) | VirPath: {len(vir_path)} hops"
    flog.info(f"   🌍 {msg_head}") 
    log.append(msg_head)
    
    current_phy = src
    
    for i in range(len(vir_path)-1):
        u_v, v_v = vir_path[i], vir_path[i+1]
        
        # --- 调试辅助函数：打印域内拓扑 ---
        def log_domain_snapshot(domain_label, nodes):
            snapshot = []
            snapshot.append(f"    🔍 [Debug] Snapshot of Domain {domain_label}:")
            snapshot.append(f"      Nodes ({len(nodes)}): {nodes}")
            link_count = 0
            # 打印域内所有链路状态
            for u in nodes:
                if u in G_phy:
                    for v in G_phy.neighbors(u):
                        if v in nodes: # 只看域内边
                            d = G_phy[u][v]
                            cap = d.get('capacity', 0)
                            used = d.get('used_bw', 0)
                            delay = d.get('delay', 0)
                            snapshot.append(f"      Link {u}<->{v}: Cap={cap}, Used={used}, Delay={delay:.1f}")
                            link_count += 1
            if link_count == 0:
                snapshot.append(f"      ⚠️ WARNING: No internal links found in this domain!")
            return snapshot
        # -----------------------------------

        # 1. 检查域节点映射
        domain_nodes = [n for n in vir_to_phy.get(u_v, []) if n in G_phy]
        if not domain_nodes:
            reason = f"Domain Empty: {u_v}"
            flog.error(f"      ❌ {reason}"); log.append(reason)
            return None, False, log, reason

        best_link, min_d = None, float('inf')
        
        # 2. 寻找物理边界
        connected = False
        for u in domain_nodes:
            for v in G_phy.neighbors(u):
                if phy_to_vir.get(v) == v_v:
                    connected = True
                    d = G_phy[u][v].get('delay', 999)
                    if d < min_d: min_d = d; best_link = (u, v)
        
        if not connected:
            reason = f"Phys-Link Break: {u_v}->{v_v}"
            flog.warning(f"      ❌ {reason}"); log.append(reason)
            
            # [新增] 打印当前域的拓扑，看看是不是边缘节点出了问题
            log.extend(log_domain_snapshot(u_v, domain_nodes))
            
            return None, False, log, reason
            
        egress, ingress = best_link
        
        # 3. 预算分解
        seg_delay = G_vir[u_v][v_v].get('delay', 10)
        local_budget = qos['delay_req'] * (seg_delay / total_est)
        req_copy = qos.copy(); req_copy['delay_req'] = local_budget
        
        msg_step = f"> Dom {u_v}: {current_phy}->{egress} | Budget: {local_budget:.1f}ms"
        flog.info(f"      {msg_step}")
        log.append(f"      {msg_step}")
        
        # 4. 域内寻路 (H-IGA)
        sub = []
        if current_phy != egress:
            try:
                sub, _ = algo_intra.find_path(G_phy, current_phy, egress, req_copy)
            except Exception as e:
                reason = f"IGA Crash: {str(e)}"
                flog.error(f"      💥 {reason}"); log.append(reason)
                return None, False, log, reason

            if not sub: 
                reason = f"Intra-Domain Fail: {current_phy}->{egress}"
                flog.warning(f"      ⚠️ {reason}"); log.append(reason)
                
                # [新增] 核心调试：为什么域内寻路失败？
                # 打印该域内的所有节点和链路状态，供人工分析
                log.extend(log_domain_snapshot(u_v, domain_nodes))
                
                return None, False, log, reason
            
            full_path.extend(sub)
            log.append(f"      [√] Path: {'->'.join(sub)}")
        else:
            full_path.append(current_phy)
            log.append(f"      [√] Direct: {current_phy}")
            
        topo_mgr.update_link_state(G_phy, egress, ingress, qos['bandwidth'])
        log.append(f"      || Cross: {egress}->{ingress} ||")
        current_phy = ingress

    # 5. 最后一段
    if current_phy != dst:
        last_req = qos.copy(); last_req['delay_req'] = qos['delay_req'] 
        flog.info(f"      🔸 [终段] 域 {vir_path[-1]}: {current_phy}->{dst}")
        
        sub, _ = algo_intra.find_path(G_phy, current_phy, dst, last_req)
        if not sub: 
            reason = f"Last-Seg Fail: {current_phy}->{dst}"
            flog.warning(f"      ⚠️ {reason}"); log.append(reason)
            
            # [新增] 打印最后一个域的拓扑
            last_domain_nodes = [n for n in vir_to_phy.get(vir_path[-1], []) if n in G_phy]
            log.extend(log_domain_snapshot(vir_path[-1], last_domain_nodes))
            
            return None, False, log, reason
            
        full_path.extend(sub)
    else:
        full_path.append(dst)
        log.append(f"      [Last]: Arrived {dst}")

    return full_path, True, log, "Success"


def main():
    flog.info("========================================================")
    flog.info(f"🚀 [HeteroSat Sim] 平行对比仿真 (最终定稿版)")
    flog.info(f"   - 结果目录: {SESSION_DIR}")
    flog.info("========================================================")

    ensure_dir(ROUTING_INFO_DIR)
    ensure_dir(RESULTS_DIR)
    
    f_dijk = open(os.path.join(ROUTING_INFO_DIR, "dijkstra_paths.txt"), 'w', encoding='utf-8')
    f_higa = open(os.path.join(ROUTING_INFO_DIR, "h_iga_paths.txt"), 'w', encoding='utf-8')

    topo_mgr = TopologyManager()
    traffic_gen = TrafficGenerator(topo_mgr)
    vtm = VirtualTopologyManager()
    
    algo_baseline = DijkstraStrategy(weight_key='delay') 
    algo_iga = IGAStrategy() 
    algo_inter = InterDomainAlgorithm() 
    
    all_results = []

    for sim_time in range(0, SIM_DURATION, TIME_STEP):
        flog.info(f"\n⏳ [Time {sim_time}s] 初始化环境...")
        
        G_base = topo_mgr.get_graph_at_time(sim_time)
        G_vir, phy_to_vir = vtm.build_virtual_graph(G_base)
        requests = manage_traffic(traffic_gen, G_base, sim_time, REQUESTS_PER_STEP)
        
        G_env_dijkstra = copy.deepcopy(G_base)
        G_env_higa = copy.deepcopy(G_base)
        
        # 4. Dijkstra
        flog.info(f"   🤖 [Group A] Running Dijkstra...")
        for req in requests:
            t0 = datetime.now()
            path, _ = algo_baseline.find_path(G_env_dijkstra, req['src'], req['dst'])
            dt = (datetime.now() - t0).total_seconds() * 1000
            
            res = {'Time': sim_time, 'ID': req['id'], 'Type': req['service_type'], 'Algo': 'Dijkstra', 'Success': bool(path), 'TimeCost': dt}
            
            if path:
                f_dijk.write(f"T={sim_time}, ID={req['id']}\n  {path}\n")
                # Dijkstra 强制塞入，触发拥塞惩罚
                for u, v in zip(path[:-1], path[1:]):
                    topo_mgr.update_link_state(G_env_dijkstra, u, v, req['bandwidth'])
                m = algo_iga._evaluate_path(G_env_dijkstra, path)
                res.update({'Delay': m['delay'], 'Loss': m['loss'], 'Hops': len(path)})
            else:
                res.update({'Delay': None, 'Loss': None, 'Hops': None})
            all_results.append(res)

        # 5. H-IGA
        flog.info(f"   🧬 [Group B] Running H-IGA...")
        for req in tqdm(requests, desc="H-IGA"):
            t0 = datetime.now()
            src_v = phy_to_vir.get(req['src'], req['src'])
            dst_v = phy_to_vir.get(req['dst'], req['dst'])
            v_path, _ = algo_inter.find_path(G_vir, src_v, dst_v, req)
            
            path, success, log, fail_reason = None, False, [], "Unknown"
            
            if v_path:
                # [修改] 接收 4 个返回值
                path, success, log, fail_reason = decompose_and_execute_hierarchical(
                    G_env_higa, G_vir, v_path, phy_to_vir, req['src'], req['dst'], req, algo_iga, topo_mgr
                )
            else:
                fail_reason = "No Virtual Path (Inter-domain fail)"
                log.append("Virtual Topology Routing Failed")
            
            dt = (datetime.now() - t0).total_seconds() * 1000
            
            # [结果字典] 保持 CSV 纯净，这里不写 Reason
            res = {
                'Time': sim_time, 'ID': req['id'], 'Type': req['service_type'], 
                'Algo': 'H-IGA', 'Success': success, 'TimeCost': dt
            }
            
            # [核心修改] 将成功和失败的详细信息都写入日志文件 h_iga_paths.txt
            f_higa.write(f"T={sim_time}, ID={req['id']} [{ 'SUCCESS' if success else 'FAILED' }]\n")
            
            if success and path:
                # 成功时：记录路径和指标
                f_higa.write(f"  Result: Success\n")
                for l in log: f_higa.write(f"  {l}\n")
                f_higa.write("\n") # 空行分隔
                
                m = algo_iga._evaluate_path(G_env_higa, path)
                res.update({'Delay': m['delay'], 'Loss': m['loss'], 'Hops': len(path)})
            else:
                # 失败时：记录原因和中断前的过程
                f_higa.write(f"  Result: FAILED\n")
                f_higa.write(f"  Reason: {fail_reason}\n") # <--- 记录失败原因
                f_higa.write(f"  Trace:\n")
                for l in log: f_higa.write(f"    {l}\n") # <--- 记录已完成的步骤
                f_higa.write("\n") # 空行分隔
                
                res.update({'Delay': None, 'Loss': None, 'Hops': None})
                
            all_results.append(res)

        log_network_snapshot(G_env_dijkstra, sim_time, "Dijkstra_World")
        log_network_snapshot(G_env_higa, sim_time, "H-IGA_World")

    f_dijk.close()
    f_higa.close()
    
    if all_results:
        df = pd.DataFrame(all_results)
        csv_path = os.path.join(SESSION_DIR, "sim_metrics_parallel.csv")
        df.to_csv(csv_path, index=False)
        print("\n📊 平行仿真结果摘要:")
        print(df[df['Success']==True].groupby(['Algo', 'Type'])[['Delay', 'Loss']].mean())
        print(f"\n📁 结果已保存: {SESSION_DIR}")

if __name__ == "__main__":
    main()