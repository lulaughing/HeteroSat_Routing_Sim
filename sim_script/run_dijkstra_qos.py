# -*- coding: utf-8 -*-
"""
Baseline 2: QoS-Dijkstra (CSPF - Constrained Shortest Path First)
逻辑: 在 Dijkstra 算路前，先剔除剩余带宽不足的链路 (剪枝)，然后找最短路。
"""
import sys
import os
# 添加项目根目录到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime
from tqdm import tqdm
from src.utils import get_flow_logger, get_net_logger, get_logger, SESSION_DIR
from src.topology import TopologyManager
from src.traffic import TrafficGenerator
# [修改] 导入 QoS-Dijkstra 算法类 (需确保 src/routing/dijkstra_qos.py 存在)
from src.routing.dijkstra_qos import QoSDijkstraAlgorithm 
from src.routing.iga.iga_fitness import evaluate_path
from src.simulation_utils import manage_traffic, log_network_snapshot, ensure_dir, get_sim_config

# 独立日志目录 (复用 run_all.py 生成的 SESSION_DIR)
LOG_DIR = os.path.join(SESSION_DIR)
ensure_dir(LOG_DIR)
# [新增] 算法详细日志
alog = get_logger('ALGO_QOS', 'algo_qos_details.log', console=False)

def main():
    print(f"🚀 [Baseline] Running QoS-Dijkstra (CSPF)...")

    # [配置] 获取仿真参数
    cfg = get_sim_config()
    sim_start = cfg['SIM_START']
    sim_duration = cfg['SIM_DURATION']
    time_step = cfg['TIME_STEP']
    req_count = cfg['REQUESTS_PER_STEP']
    
    print(f"   ⚙️ Config: Start={sim_start}s, Duration={sim_duration}s, Step={time_step}s, Reqs={req_count}")
    
    topo_mgr = TopologyManager()
    traffic_gen = TrafficGenerator(topo_mgr)
    
    # [关键修改] 实例化 QoS-Dijkstra 算法，传入详细日志记录器
    algo = QoSDijkstraAlgorithm(logger=alog)
    
    results = []
    
    # [新增] 记录详细路径信息
    f_path = open(os.path.join(LOG_DIR, "dijkstra_qos_paths.txt"), 'w', encoding='utf-8')
    
    for t in range(sim_start, sim_start + sim_duration, time_step): 
        G = topo_mgr.get_graph_at_time(t)
        
        # 加载流量
        requests = manage_traffic(traffic_gen, G, t, req_count, "data/traffic")
        
        for req in tqdm(requests, desc="QoS-Dijkstra"):
            t0 = datetime.now()
            
            # [关键修改] 调用算法
            # 注意：这里传入 req 是为了让算法获取 req['bandwidth'] 进行剪枝
            path, success = algo.find_path(G, req['src'], req['dst'], req)
            
            dt = (datetime.now() - t0).total_seconds() * 1000
            
            # 记录基础结果
            res = {
                'ID': req['id'], 
                'Type': req['service_type'], 
                'Algo': 'QoS-Dijkstra', 
                'Success': success, 
                'TimeCost': dt
            }
            
            # [新增] 写入路径日志
            f_path.write(f"ID={req['id']} [{ 'OK' if success else 'FAIL' }] ({req['service_type']})\n")
            f_path.write(f"  Req: {req['src']} -> {req['dst']} (BW: {req['bandwidth']}M)\n")
            
            if success:
                # [状态更新] 扣除链路带宽 (模拟拥塞的关键步骤)
                # 这会影响后续业务算路时的"剩余带宽"
                for u, v in zip(path[:-1], path[1:]):
                    topo_mgr.update_link_state(G, u, v, req['bandwidth'])
                
                # [指标计算] 统一使用 IGA 的评估函数计算 Delay/Loss
                m = evaluate_path(G, path)
                res.update({'Delay': m['delay'], 'Loss': m['loss'], 'Hops': len(path)})
                
                f_path.write(f"  Path: {' -> '.join(path)}\n")
                f_path.write(f"  Metrics: Delay={m['delay']:.2f}ms, Loss={m['loss']*100:.4f}%\n")
            else:
                # 失败记录
                res.update({'Delay': None, 'Loss': None, 'Hops': None, 'Note': 'No Bandwidth Path'})
                f_path.write(f"  Reason: No Bandwidth Satisfied Path\n")
            
            f_path.write("\n")
            results.append(res)
            
        # (可选) 记录网络快照日志
        # log_network_snapshot(None, G, t, "QoS-Dijkstra")
    
    f_path.close()
    # 保存结果到 CSV
    output_path = os.path.join(LOG_DIR, "metrics_dijkstra_qos.csv")
    df = pd.DataFrame(results)
    df.to_csv(output_path, index=False)
    print(f"✅ QoS-Dijkstra Finished. Results saved to {output_path}")

if __name__ == "__main__":
    main()