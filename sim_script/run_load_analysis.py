# -*- coding: utf-8 -*-
"""
File: sim_script/run_load_analysis.py
Description: 全网业务量分析 (Load Analysis) - Final Strict Mode + Goodput
功能: 
1. 遍历负载梯度 (50 -> 600)
2. 对比 H-IGA vs SGA vs Dijkstra
3. 统计指标: PDR, Delay, Loss, Throughput, Goodput (有效吞吐)
"""
import sys
import os
import pandas as pd
from tqdm import tqdm
import time
import networkx as nx
import copy

# 路径设置
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- 核心模块导入 ---
from src.topology import TopologyManager
from src.traffic import TrafficGenerator
from src.utils import get_logger

from src.routing.hierarchical_mapper import VirtualTopologyManager 

from src.simulation_utils import (
    manage_traffic, 
    decompose_and_execute_hierarchical, 
    get_sim_config,
    ensure_dir
)

# --- 算法策略导入 ---
from src.routing.iga.iga import IGAStrategy
from src.routing.sga import SGAStrategy
from src.routing.dijkstra import DijkstraStrategy
import src.routing.iga.iga_fitness as iga_fitness_module

# 配置日志
logger = get_logger("LoadAnalysis", "load_analysis.log")

def run_load_experiment(n_requests, topo_mgr, traffic_gen, vtm, base_dir):
    """
    运行指定负载 (n_requests) 下的多算法对比实验
    """
    # 1. 设定 H-IGA 参数
    iga_fitness_module.GAMMA = 3.0 
    iga_fitness_module.LAMBDA = 1.0
    
    # 2. 定义对比算法组
    algorithms = [
        (IGAStrategy(pop_size=20, max_iter=20, p_guide=0.6), "H-IGA"),      # 本文方法
        (SGAStrategy(pop_size=20, max_iter=20), "SGA"),                     # 对比方法1
        (DijkstraStrategy(weight_key='delay'), "Dijkstra")                  # 对比方法2 (基准)
    ]
    
    t = 300 # 选取一个典型的时间片 
    results = []
    print(f"\n⚖️ [Load Test] Running Load = {n_requests} flows...")

    # A. 准备环境
    G_phy_base = topo_mgr.get_graph_at_time(t)
    G_vir_base, phy_to_vir = vtm.build_virtual_graph(G_phy_base)
    
    # B. 生成统一流量
    traffic_dir = os.path.join("data", "traffic_cache_load_analysis")
    ensure_dir(traffic_dir)
    requests = manage_traffic(traffic_gen, G_phy_base, t, n_requests, traffic_dir)
    
    # C. 遍历算法
    for algo, algo_name in algorithms:
        # 深拷贝环境
        G_phy_run = copy.deepcopy(G_phy_base)
        G_vir_run = copy.deepcopy(G_vir_base)
        
        # 彻底重置带宽占用
        for u, v, d in G_phy_run.edges(data=True):
            d['used_bw'] = 0.0
        
        pbar = tqdm(requests, desc=f"   Algo={algo_name}", leave=False)
        
        for req in pbar:
            src, dst = req['src'], req['dst']
            bw = req['bandwidth']
            
            # --- 1. 算法寻路 (控制平面) ---
            path, found, note = None, False, "Unknown"

            if algo_name == "Dijkstra":
                try:
                    path = nx.dijkstra_path(G_phy_run, src, dst, weight='delay')
                    found = True
                    note = "PathFound"
                except nx.NetworkXNoPath:
                    path = None
                    found = False
                    note = "NoPath"
            
            elif algo_name == "H-IGA":
                from src.routing.inter_algo import InterDomainAlgorithm
                algo_inter = InterDomainAlgorithm()
                s_vir = phy_to_vir.get(src, src)
                d_vir = phy_to_vir.get(dst, dst)
                
                path_vir, _ = algo_inter.find_path(G_vir_run, s_vir, d_vir, req)
                
                if not path_vir:
                    path, found, note = None, False, "Inter-Fail"
                else:
                    path, found, _, note = decompose_and_execute_hierarchical(
                        None, G_phy_run, G_vir_run, path_vir, phy_to_vir, src, dst, req, algo, topo_mgr
                    )

            elif algo_name == "SGA":
                path, _ = algo.find_path(G_phy_run, src, dst, req)
                found = (path is not None)
                note = "PathFound" if found else "Fail"

            # --- 2. 状态更新 (物理层模拟) ---
            if found and path and algo_name in ["Dijkstra", "SGA"]:
                for i in range(len(path) - 1):
                    u_hop, v_hop = path[i], path[i+1]
                    topo_mgr.update_link_state(G_phy_run, u_hop, v_hop, bw)

            # --- 3. 结果严格判决 (数据平面) ---
            # [关键设定] 恢复严谨模式
            LOSS_THRESHOLD = 1.0
            
            real_success = False
            path_metrics = {'delay': 0, 'loss': 1.0, 'max_util': 0.0}

            if found and path:
                # 计算物理指标 (含拥塞惩罚)
                path_metrics = iga_fitness_module.evaluate_path(G_phy_run, path)
                
                if path_metrics['loss'] <= LOSS_THRESHOLD:
                    real_success = True
                else:
                    real_success = False
                    note = f"HighLoss ({path_metrics['loss']:.1%})"
            else:
                real_success = False

            # --- 4. 数据记录 (含 Goodput 计算) ---
            
            # [新增] 计算单条业务的有效吞吐 (Goodput)
            # 定义: 尝试发送的带宽 * (1 - 丢包率)
            # 如果失败(Loss>Threshold)，则 Goodput = 0 (或者极其微小，这里按0处理更严谨)
            real_goodput = 0.0
            if real_success:
                real_goodput = bw * (1.0 - path_metrics['loss'])
                if real_goodput < 0: real_goodput = 0

            if real_success:
                results.append({
                    'ID': req['id'], 'Algo': algo_name, 'Load': n_requests,
                    'Success': True, 
                    'Bandwidth': bw,
                    'Goodput': real_goodput,  # [New]
                    'Delay': path_metrics['delay'], 
                    'Loss': path_metrics['loss'],
                    'Hops': len(path),
                    'MaxUtil': path_metrics['max_util']
                })
            else:
                # 失败记录
                results.append({
                    'ID': req['id'], 'Algo': algo_name, 'Load': n_requests,
                    'Success': False, 
                    'Bandwidth': bw,
                    'Goodput': 0.0,           # [New] 失败业务无有效产出
                    'Delay': path_metrics['delay'] if path else 0, 
                    'Loss': path_metrics['loss'], 
                    'Hops': len(path) if path else 0,
                    'MaxUtil': path_metrics['max_util'] if path else 0,
                    'Note': note
                })

    df = pd.DataFrame(results)
    csv_path = os.path.join(base_dir, f"metrics_load_{n_requests}.csv")
    df.to_csv(csv_path, index=False)
    return df

def main():
    # ==========================================
    # [配置区] 仿真规模控制
    # ==========================================
    # 模式 1: 冒烟测试
    # LOADS_TO_TEST = [10, 20] 
    
    # 模式 2: 全量测试 (建议直接运行此项)
    # LOADS_TO_TEST = [50, 100, 200, 300, 400, 500, 600]
    # 推荐的细化配置
    LOADS_TO_TEST = [10, 30, 50, 80, 100, 150, 200, 250, 300, 400, 500, 600]
    
    print(f"🚀 [Load Analysis] Started (Strict Mode + Goodput).")
    print(f"📈 Testing Load Levels: {LOADS_TO_TEST}")
    
    session_time = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join("logs", f"load_analysis_{session_time}")
    ensure_dir(out_dir)
    print(f"📂 Results will be saved to: {out_dir}")
    
    # 初始化核心组件
    topo_mgr = TopologyManager()
    traffic_gen = TrafficGenerator(topo_mgr)
    vtm = VirtualTopologyManager()
    
    # 汇总数据
    summary = []

    # 循环执行
    for n in LOADS_TO_TEST:
        try:
            df = run_load_experiment(n, topo_mgr, traffic_gen, vtm, out_dir)
            
            # 打印本轮简报
            print(f"\n📊 Summary for Load = {n}:")
            for algo in ["H-IGA", "SGA", "Dijkstra"]:
                sub = df[df['Algo'] == algo]
                
                # 1. PDR
                pdr = sub['Success'].mean() * 100 if not sub.empty else 0
                
                # 2. Avg Delay (只算成功的)
                succ_df = sub[sub['Success'] == True]
                avg_delay = succ_df['Delay'].mean() if not succ_df.empty else 0
                
                # 3. Throughput (准入流量)
                thr = succ_df['Bandwidth'].sum() if not succ_df.empty else 0
                
                # 4. Avg Goodput (有效流量) [New]
                # 注意：是对所有业务求和（失败的Goodput为0）
                goodput = sub['Goodput'].sum() if not sub.empty else 0
                
                # 5. Avg Loss
                avg_loss = sub['Loss'].mean() * 100 if not sub.empty else 0
                
                print(f"   >> {algo:<8}: PDR={pdr:5.1f}% | Goodput={goodput:6.1f} Mbps | Delay={avg_delay:6.1f} ms | Loss={avg_loss:5.1f}%")
                
                summary.append({
                    'Load': n, 'Algo': algo, 
                    'PDR': pdr, 
                    'Throughput': thr,      # 准入
                    'AvgGoodput': goodput,  # 有效 [New]
                    'AvgDelay': avg_delay,
                    'AvgLoss': avg_loss
                })
                
        except Exception as e:
            logger.error(f"Error at Load={n}: {e}")
            print(f"❌ Error at Load={n}: {e}")
            import traceback
            traceback.print_exc()
            
    # 保存汇总数据
    summary_df = pd.DataFrame(summary)
    summary_path = os.path.join(out_dir, "summary_all_loads.csv")
    summary_df.to_csv(summary_path, index=False)
    
    print(f"\n✅ All experiments finished. Final Summary saved to: {summary_path}")

if __name__ == '__main__':
    main()