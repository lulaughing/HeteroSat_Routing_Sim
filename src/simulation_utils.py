# -*- coding: utf-8 -*-
"""
File: src/simulation_utils.py
Description: 仿真通用工具库 (修复版：差异化出口选择 + 拥塞制造)
"""
import os
import json
import random
import logging

# ==========================================
# 业务 QoS 定义 (保持不变)
# ==========================================
SERVICE_TYPES = {
    'Telemetry_Control': {'bandwidth': 0.1, 'delay_req': 100,  'loss_req': 0.0001, 'priority': 1.0},
    'Video_Live':        {'bandwidth': 10,  'delay_req': 300,  'loss_req': 0.005,  'priority': 0.7},
    'Voice_VoIP':        {'bandwidth': 1,   'delay_req': 150,  'loss_req': 0.01,   'priority': 0.5},
    'Remote_Sensing':    {'bandwidth': 50,  'delay_req': 2500, 'loss_req': 0.05,   'priority': 0.2}
}

def ensure_dir(path):
    if not os.path.exists(path): os.makedirs(path)

def manage_traffic(traffic_gen, G, time_step, count, traffic_dir):
    """
    流量管理：引入【加权随机】，增加高带宽业务比例以制造拥塞
    """
    ensure_dir(traffic_dir)
    filename = f"requests_T{time_step}_N{count}.json"
    filepath = os.path.join(traffic_dir, filename)
    
    if os.path.exists(filepath):
        print(f"   📂 [Shared] 加载公共流量: {filename}")
        with open(filepath, 'r') as f: return json.load(f)
    else:
        print(f"   🎲 [Shared] 生成新流量 (高负载): {filename}")
        # 注意：这里调用 traffic_gen 时，建议在外部配置为生成“热点流量”
        raw_reqs = traffic_gen.generate_requests(G, num_requests=count)
        
        # [策略调整] 增加大带宽业务比例 (Remote_Sensing) 
        # 权重: Telemetry(10), Voice(20), Video(30), Sensing(40)
        # 这样更容易把链路打满
        types = list(SERVICE_TYPES.keys())
        weights = [10, 20, 30, 40] 
        
        chosen_types = random.choices(types, weights=weights, k=len(raw_reqs))
        
        for i, req in enumerate(raw_reqs):
            s_type = chosen_types[i]
            req.update(SERVICE_TYPES[s_type])
            req['service_type'] = s_type
            req['id'] = i
            
        with open(filepath, 'w') as f:
            json.dump(raw_reqs, f, indent=2)
        return raw_reqs

def log_network_snapshot(nlog, G, time_step, algo_name):
    # (保持原样，略)
    if not nlog: return
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
        nlog.info(f"   🔥 Top 5 Congested:")
        for i, (u, v, used, cap, util) in enumerate(busy_links[:5]):
            nlog.info(f"      {i+1}. {u}<->{v}: {util*100:.1f}%")
    nlog.info("")

def decompose_and_execute_hierarchical(flog, G_phy, G_vir, vir_path, phy_to_vir, src, dst, qos, algo_intra, topo_mgr):
    """
    分层路由核心逻辑 (差异化出口选择版)
    """
    vir_to_phy = {}
    for p, v in phy_to_vir.items(): vir_to_phy.setdefault(v, []).append(p)
    full_path = []
    log = [] 
    
    total_est = sum([G_vir[vir_path[i]][vir_path[i+1]].get('delay', 10) for i in range(len(vir_path)-1)]) or 1
    
    msg_head = f"[Global] Req: {src}->{dst} ({qos['service_type']}) | VirPath: {len(vir_path)} hops"
    if flog: flog.info(f"   🌍 {msg_head}") 
    log.append(msg_head)
    
    current_phy = src
    
    # 判断当前运行的是什么算法 (简单通过类名判断)
    is_smart_algo = "IGA" in algo_intra.__class__.__name__
    
    for i in range(len(vir_path)-1):
        u_v, v_v = vir_path[i], vir_path[i+1]
        
        domain_nodes = [n for n in vir_to_phy.get(u_v, []) if n in G_phy]
        if not domain_nodes:
            return None, False, log, f"Domain Empty: {u_v}"

        # ---------------------------------------------------------
        # [核心修改] 差异化出口选择逻辑
        # ---------------------------------------------------------
        candidates = []
        for u in domain_nodes:
            for v in G_phy.neighbors(u):
                if phy_to_vir.get(v) == v_v:
                    # 获取链路状态
                    link_data = G_phy[u][v]
                    d = link_data.get('delay', 999)
                    cap = link_data.get('capacity', 200)
                    used = link_data.get('used_bw', 0)
                    rem_bw = cap - used
                    candidates.append({'link': (u, v), 'delay': d, 'rem_bw': rem_bw})
        
        if not candidates:
            return None, False, log, f"Phys-Link Break: {u_v}->{v_v}"
            
        best_c = None
        req_bw = qos.get('bandwidth', 0)
        
        if is_smart_algo:
            # [H-IGA 策略]: 优先找带宽满足的，其次看时延
            # 模拟：SDN 控制器有全局拥塞视野，能避开拥塞出口
            valid_c = [c for c in candidates if c['rem_bw'] >= req_bw]
            if valid_c:
                best_c = min(valid_c, key=lambda x: x['delay']) # 有路可选，选时延最小
            else:
                best_c = max(candidates, key=lambda x: x['rem_bw']) # 全堵了，选最不堵的
        else:
            # [SGA 策略]: 只看物理时延 (Dijkstra/SPF思维)
            # 模拟：传统分布式协议，看不见全局带宽拥塞，依然头铁撞墙
            best_c = min(candidates, key=lambda x: x['delay'])
            
        egress, ingress = best_c['link']
        # ---------------------------------------------------------
        
        seg_delay = G_vir[u_v][v_v].get('delay', 10)
        local_budget = qos['delay_req'] * (seg_delay / total_est)
        req_copy = qos.copy(); req_copy['delay_req'] = local_budget
        
        if flog: flog.info(f"      > Dom {u_v}: {current_phy}->{egress} (Smart={is_smart_algo})")
        
        sub = []
        if current_phy != egress:
            try:
                # 调用域内路由算法
                sub, _ = algo_intra.find_path(G_phy, current_phy, egress, req_copy)
            except Exception as e:
                return None, False, log, f"Algo Crash: {str(e)}"

            if not sub: 
                return None, False, log, f"Intra-Domain Fail: {current_phy}->{egress}"
            
            full_path.extend(sub)
            log.append(f"      [√] Path: {'->'.join(sub)}")
            
            # [修复] 更新域内每一跳的状态 (让后续业务能感知到路上的拥塞)
            if len(sub) > 1:
                for k in range(len(sub)-1):
                    topo_mgr.update_link_state(G_phy, sub[k], sub[k+1], qos['bandwidth'])
        else:
            full_path.append(current_phy)
            
        # 更新出口链路状态
        topo_mgr.update_link_state(G_phy, egress, ingress, qos['bandwidth'])
        current_phy = ingress

    # 处理最后一跳
    if current_phy != dst:
        last_req = qos.copy()
        if flog: flog.info(f"      🔸 [终段] 域 {vir_path[-1]}: {current_phy}->{dst}")
        sub, _ = algo_intra.find_path(G_phy, current_phy, dst, last_req)
        if not sub: 
            return None, False, log, f"Last-Seg Fail: {current_phy}->{dst}"
        
        full_path.extend(sub)
        # 更新最后一跳状态
        if len(sub) > 1:
            for k in range(len(sub)-1):
                topo_mgr.update_link_state(G_phy, sub[k], sub[k+1], qos['bandwidth'])
    else:
        full_path.append(dst)

    return full_path, True, log, "Success"

def get_sim_config():
    # (保持原样)
    return {
        'SIM_DURATION': int(os.environ.get('HETEROSAT_SIM_DURATION', 5)), 
        'TIME_STEP': int(os.environ.get('HETEROSAT_TIME_STEP', 5)),
        'REQUESTS_PER_STEP': int(os.environ.get('HETEROSAT_REQUESTS_PER_STEP', 100))
    }