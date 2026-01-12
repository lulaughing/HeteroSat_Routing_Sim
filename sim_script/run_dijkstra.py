# -*- coding: utf-8 -*-
"""
Baseline 1: Dijkstra (Flat, No QoS, Shortest Delay)
"""
import sys
import os
# 添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime
from tqdm import tqdm
from src.utils import get_flow_logger, get_net_logger, SESSION_DIR
from src.topology import TopologyManager
from src.traffic import TrafficGenerator
from src.routing.dijkstra import DijkstraStrategy
from src.routing.iga.iga_fitness import evaluate_path
from src.simulation_utils import manage_traffic, log_network_snapshot, ensure_dir, get_sim_config # <--- 引入 get_sim_config

# 独立日志目录
LOG_DIR = os.path.join(SESSION_DIR)
ensure_dir(LOG_DIR)

def main():
    print(f"🚀 [Baseline] Running Dijkstra (Flat Topology)...")

    # [新增] 获取配置
    cfg = get_sim_config()
    sim_duration = cfg['SIM_DURATION']
    time_step = cfg['TIME_STEP']
    req_count = cfg['REQUESTS_PER_STEP']
    
    print(f"   ⚙️ Config: Duration={sim_duration}s, Step={time_step}s, Reqs={req_count}")
    
    topo_mgr = TopologyManager()
    traffic_gen = TrafficGenerator(topo_mgr)
    
    # 扁平化路由，不需要 VTM 和 InterAlgo
    algo = DijkstraStrategy(weight_key='delay')
    
    results = []
    
    for t in range(0, sim_duration, time_step): 
        G = topo_mgr.get_graph_at_time(t)
        # [修改] 使用配置的请求数量
        requests = manage_traffic(traffic_gen, G, t, req_count, "data/traffic")
        
        for req in tqdm(requests, desc="Dijkstra"):
            t0 = datetime.now()
            # 扁平路由：直接在物理图上算
            path, _ = algo.find_path(G, req['src'], req['dst'])
            dt = (datetime.now() - t0).total_seconds() * 1000
            
            success = bool(path)
            res = {'ID': req['id'], 'Type': req['service_type'], 'Algo': 'Dijkstra', 'Success': success, 'TimeCost': dt}
            
            if success:
                # 关键：更新物理状态 (模拟拥塞)
                for u, v in zip(path[:-1], path[1:]):
                    topo_mgr.update_link_state(G, u, v, req['bandwidth'])
                
                # 统一使用 IGA 的 evaluate_path 计算指标
                m = evaluate_path(G, path)
                res.update({'Delay': m['delay'], 'Loss': m['loss'], 'Hops': len(path)})
            else:
                res.update({'Delay': None, 'Loss': None, 'Hops': None})
            
            results.append(res)
            
        # 记录网络快照
        # 注意：这里需要自己初始化 logger 或者传入 None
        # 为简化，这里暂不打印详细 log 到文件，只跑数据
    
    df = pd.DataFrame(results)
    df.to_csv(os.path.join(LOG_DIR, "metrics_dijkstra.csv"), index=False)
    print("✅ Dijkstra Finished.")

if __name__ == "__main__":
    main()