# -*- coding: utf-8 -*-
"""
Experimental: H-IGA (Hierarchical, Intelligent, Congestion Aware)
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime
from tqdm import tqdm
from src.utils import get_flow_logger, SESSION_DIR, get_net_logger
from src.topology import TopologyManager
from src.traffic import TrafficGenerator
from src.routing.hierarchical_mapper import VirtualTopologyManager
from src.routing.inter_algo import InterDomainAlgorithm
from src.routing.iga.iga import IGAStrategy
from src.routing.iga.iga_fitness import evaluate_path
# <--- 引入 log_network_snapshot
from src.simulation_utils import manage_traffic, decompose_and_execute_hierarchical, log_network_snapshot, ensure_dir, get_sim_config

LOG_DIR = os.path.join(SESSION_DIR)
ensure_dir(LOG_DIR)
flog = get_flow_logger() # H-IGA 我们需要详细日志
nlog = get_net_logger() # <--- 初始化网络状态日志

def main():
    print(f"🚀 [Experiment] Running H-IGA (The Proposed Method)...")
    # [新增] 获取配置
    cfg = get_sim_config()
    sim_duration = cfg['SIM_DURATION']
    time_step = cfg['TIME_STEP']
    req_count = cfg['REQUESTS_PER_STEP']
    
    print(f"   ⚙️ Config: Duration={sim_duration}s, Step={time_step}s, Reqs={req_count}")
    
    topo_mgr = TopologyManager()
    traffic_gen = TrafficGenerator(topo_mgr)
    vtm = VirtualTopologyManager()
    
    algo_inter = InterDomainAlgorithm()
    algo_intra = IGAStrategy() # 使用 H-IGA
    
    results = []
    
    # 记录详细路径信息
    f_path = open(os.path.join(LOG_DIR, "h_iga_paths.txt"), 'w', encoding='utf-8')

    
    for t in range(0, sim_duration, time_step):
        G_phy = topo_mgr.get_graph_at_time(t)
        G_vir, phy_to_vir = vtm.build_virtual_graph(G_phy)
        requests = manage_traffic(traffic_gen, G_phy, t, req_count, "data/traffic")
        
        for req in tqdm(requests, desc="H-IGA"):
            t0 = datetime.now()
            
            src_v = phy_to_vir.get(req['src'], req['src'])
            dst_v = phy_to_vir.get(req['dst'], req['dst'])
            v_path, _ = algo_inter.find_path(G_vir, src_v, dst_v, req)
            
            path, success, log, fail_reason = None, False, [], "Unknown"
            
            if v_path:
                path, success, log, fail_reason = decompose_and_execute_hierarchical(
                    flog, G_phy, G_vir, v_path, phy_to_vir, 
                    req['src'], req['dst'], req, 
                    algo_intra, # <--- 传入 IGA
                    topo_mgr
                )
            else:
                fail_reason = "No Virtual Path"
            
            dt = (datetime.now() - t0).total_seconds() * 1000
            res = {'ID': req['id'], 'Type': req['service_type'], 'Algo': 'H-IGA', 'Success': success, 'TimeCost': dt, 'Note': fail_reason if not success else ""}
            
            f_path.write(f"ID={req['id']} [{ 'OK' if success else 'FAIL' }]\n")
            if success and path:
                m = evaluate_path(G_phy, path)
                res.update({'Delay': m['delay'], 'Loss': m['loss'], 'Hops': len(path)})
                for l in log: f_path.write(f"  {l}\n")
            else:
                f_path.write(f"  Reason: {fail_reason}\n")
                res.update({'Delay': None, 'Loss': None, 'Hops': None})
            f_path.write("\n")
            
            results.append(res)

        # 当这一秒的所有业务都分配完带宽后，打印当前的链路拥塞情况
        log_network_snapshot(nlog, G_phy, t, "H-IGA")

    f_path.close()
    df = pd.DataFrame(results)
    df.to_csv(os.path.join(LOG_DIR, "metrics_higa.csv"), index=False)
    print("✅ H-IGA Finished.")

if __name__ == "__main__":
    main()