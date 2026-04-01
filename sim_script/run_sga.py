# -*- coding: utf-8 -*-
"""
Baseline 2: SGA (Hierarchical, Random Init, No Congestion Awareness)
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime
from tqdm import tqdm
# [修改 1] 引入 get_net_logger
from src.utils import get_flow_logger, get_net_logger, get_session_dir
from src.topology import TopologyManager
from src.traffic import TrafficGenerator
from src.routing.hierarchical_mapper import VirtualTopologyManager
from src.routing.inter_algo import InterDomainAlgorithm
from src.routing.sga import SGAStrategy 
from src.routing.iga.iga_fitness import evaluate_path
# [修改 2] 引入 log_network_snapshot
from src.simulation_utils import manage_traffic, decompose_and_execute_hierarchical, log_network_snapshot, ensure_dir, get_sim_config

def main():
    print(f"[Baseline] Running SGA (Hierarchical)...")
    log_dir = get_session_dir()
    ensure_dir(log_dir)

    # 获取配置
    cfg = get_sim_config()
    sim_start = cfg['SIM_START']
    sim_duration = cfg['SIM_DURATION']
    time_step = cfg['TIME_STEP']
    req_count = cfg['REQUESTS_PER_STEP']
    
    print(f"   Config: Start={sim_start}s, Duration={sim_duration}s, Step={time_step}s, Reqs={req_count}")
    
    # [修改 3] 初始化日志句柄
    flog = get_flow_logger() 
    nlog = get_net_logger()  # 用于记录拥塞快照
    
    topo_mgr = TopologyManager()
    traffic_gen = TrafficGenerator(topo_mgr)
    vtm = VirtualTopologyManager()
    
    algo_inter = InterDomainAlgorithm()
    algo_intra = SGAStrategy() # 使用标准 GA
    
    results = []
    
    for t in range(sim_start, sim_start + sim_duration, time_step): 
        G_phy = topo_mgr.get_graph_at_time(t)
        G_vir, phy_to_vir = vtm.build_virtual_graph(G_phy)
        requests = manage_traffic(traffic_gen, G_phy, t, req_count, "data/traffic")
        
        for req in tqdm(requests, desc="SGA"):
            t0 = datetime.now()
            
            # 1. 域间路由
            src_v = phy_to_vir.get(req['src'], req['src'])
            dst_v = phy_to_vir.get(req['dst'], req['dst'])
            v_path, _ = algo_inter.find_path(G_vir, src_v, dst_v, req)
            
            path, success = None, False
            fail_reason = "No Virtual Path"
            
            if v_path:
                # 2. 域内分解 (使用 SGA)
                path, success, _, fail_reason = decompose_and_execute_hierarchical(
                    flog, G_phy, G_vir, v_path, phy_to_vir, 
                    req['src'], req['dst'], req, 
                    algo_intra, # <--- 传入 SGA
                    topo_mgr
                )
            
            dt = (datetime.now() - t0).total_seconds() * 1000
            res = {'ID': req['id'], 'Type': req['service_type'], 'Algo': 'SGA', 'Success': success, 'TimeCost': dt, 'Note': fail_reason if not success else ""}
            
            if success and path:
                m = evaluate_path(G_phy, path)
                res.update({'Delay': m['delay'], 'Loss': m['loss'], 'Hops': len(path)})
            else:
                res.update({'Delay': None, 'Loss': None, 'Hops': None})
            results.append(res)

        # [修改 4] 记录本时间步的网络拥塞快照
        # 这对于对比 SGA 是否把某些链路“堵死”非常重要
        log_network_snapshot(nlog, G_phy, t, "SGA")

    df = pd.DataFrame(results)
    df.to_csv(os.path.join(log_dir, "metrics_sga.csv"), index=False)
    print("SGA Finished.")

if __name__ == "__main__":
    main()
