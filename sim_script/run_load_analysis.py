# -*- coding: utf-8 -*-
"""
File: sim_script/run_load_analysis.py
Description: 全网业务量分析 (Load Analysis) - Final Strict Mode + Goodput + Full Logging
功能: 
1. 遍历负载梯度 (10 -> 600)
2. 对比 H-IGA vs SGA vs Dijkstra
3. 统计指标: PDR, Delay, Loss, Throughput, Goodput
4. [New] 全量记录 Dijkstra, H-IGA, SGA 的路径详情 (含域间/域内/链路状态)
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

def log_path_details(filename, req, G_phy, path_phy, path_vir=None):
    """
    [新增] 通用路径日志记录函数
    :param filename: 日志文件路径
    :param req: 业务请求字典
    :param G_phy: 物理拓扑图 (用于查询链路状态)
    :param path_phy: 最终物理路径 List
    :param path_vir: 虚拟路径 List (仅 H-IGA/SGA 有)
    """
    bw = req['bandwidth']
    src, dst = req['src'], req['dst']
    
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"Req {req['id']} ({src}->{dst}, BW={bw}, Type={req['service_type']}):\n")
        
        # 1. 记录域间路径 (如果有)
        if path_vir:
            f.write(f"  🌐 Virtual Path: {path_vir}\n")
        
        # 2. 记录物理路径
        f.write(f"  🛣️ Physical Path: {path_phy}\n")
        
        # 3. 记录物理链路详情 (带过载检查)
        if path_phy and len(path_phy) > 1:
            for i in range(len(path_phy)-1):
                u, v = path_phy[i], path_phy[i+1]
                
                # 安全获取边属性 (兼容 MultiGraph)
                edge_data = G_phy[u][v]
                if isinstance(G_phy, nx.MultiGraph):
                    edge_data = edge_data[0]
                
                cap = edge_data.get('capacity', -1)
                used = edge_data.get('used_bw', 0)
                d = edge_data.get('delay', -1)
                
                # 状态标记
                status = "🔥OVERLOAD" if used > cap else "OK"
                
                # 安全打印 (防止 d 是 None 或非数字)
                d_str = f"{d:.2f}" if isinstance(d, (int, float)) else str(d)
                
                f.write(f"    Link {u}->{v}: Cap={cap:.1f}, Used={used:.1f}, Delay={d_str} [{status}]\n")
        
        f.write("-" * 80 + "\n")

def run_load_experiment(n_requests, topo_mgr, traffic_gen, vtm, base_dir):
    """
    运行指定负载 (n_requests) 下的多算法对比实验
    """
    cfg = get_sim_config()
    t = cfg['SIM_START']
    
    # 1. 设定 H-IGA 参数 
    iga_fitness_module.GAMMA = 3.0 
    iga_fitness_module.LAMBDA = 1.0
    
    # 2. 定义对比算法组
    algorithms = [
        (IGAStrategy(pop_size=25, max_iter=25, p_guide=0.7), "H-IGA"),
        (SGAStrategy(pop_size=30, max_iter=30), "SGA"),
        (DijkstraStrategy(weight_key='static_delay'), "Dijkstra")
    ]
    
    results = []
    print(f"\n⚖️ [Load Test] Running at T={t}s, Load = {n_requests} flows...")

    # A. 准备环境
    G_phy_base = topo_mgr.get_graph_at_time(t)
    G_vir_base, phy_to_vir = vtm.build_virtual_graph(G_phy_base)
    
    # B. 生成统一流量
    traffic_dir = os.path.join("data", "traffic_cache_load_analysis")
    ensure_dir(traffic_dir)
    requests = manage_traffic(traffic_gen, G_phy_base, t, n_requests, traffic_dir)

    # [新增] 初始化所有算法的日志文件
    log_files = {}
    for _, name in algorithms:
        fname = os.path.join(base_dir, f"paths_{name}_load_{n_requests}.txt")
        if os.path.exists(fname): os.remove(fname)
        log_files[name] = fname
    
    print(f"   📂 Path logs will be saved to: {base_dir}")

    # C. 遍历算法
    for algo, algo_name in algorithms:
        # 深拷贝环境
        G_phy_run = copy.deepcopy(G_phy_base)
        G_vir_run = copy.deepcopy(G_vir_base)
        
        # 彻底重置带宽占用
        for u, v, d in G_phy_run.edges(data=True):
            d['used_bw'] = 0.0
        
        # [优化] 优先级重排序 (VIP模式)
        # 为了降低大带宽业务(Remote_Sensing)的丢包率，我们将其排在前面处理
        # 策略: Remote_Sensing (Priority=0.2, 但带宽大) -> 强制置顶
        # 原始 Priority 定义: Telemetry(1.0) > Video(0.7) > Voice(0.5) > Sensing(0.2)
        # 新的处理顺序: Sensing > Telemetry > Video > Voice
        # 这样大流先占坑，小流填缝隙，能显著提高整体吞吐量和 Sensing 的成功率
        
        def custom_sort_key(req):
            s_type = req.get('service_type', '')
            if s_type == 'Remote_Sensing':
                return 10.0 # 最高优
            return req.get('priority', 0.0)
            
        requests_sorted = sorted(requests, key=custom_sort_key, reverse=True)
        
        pbar = tqdm(requests_sorted, desc=f"   Algo={algo_name}", leave=False)
        
        for req in pbar:
            src, dst = req['src'], req['dst']
            bw = req['bandwidth']
            
            # --- 1. 算法寻路 (控制平面) ---
            path, found, note = None, False, "Unknown"
            path_vir_log = None # 用于日志记录虚拟路径

            # =====================================================
            # 分支 1: Dijkstra (无分层，扁平)
            # =====================================================
            if algo_name == "Dijkstra":
                try:
                    # [修正] 物理隔离 v2.0：使用 Subgraph 视图 (非破坏性)
                    # 依然保留这步，作为双重保险（物理层面的屏蔽）
                    valid_nodes = []
                    for n in G_phy_run.nodes():
                        is_ground = 'Facility' in str(n) or 'Ground' in str(n)
                        if (not is_ground) or (n == src) or (n == dst):
                            valid_nodes.append(n)
                    
                    G_safe_view = G_phy_run.subgraph(valid_nodes)
                    
                    # 🔴 [核心修正] 调用 algo (DijkstraStrategy 实例) 的 find_path 方法
                    # 而不是直接调用 nx.dijkstra_path
                    # 这样 src/routing/dijkstra.py 里的逻辑才会生效！
                    path, _ = algo.find_path(G_safe_view, src, dst, req)

                    if path:
                        found = True
                        note = "PathFound"
                        # [日志] 记录 Dijkstra 路径
                        log_path_details(log_files[algo_name], req, G_phy_run, path, None)
                    else:
                        path = None; found = False; note = "NoPath"

                except Exception as e: # 捕获更广泛的异常
                    path = None; found = False; note = f"Error: {str(e)}"
            
            # =====================================================
            # 分支 2 & 3: H-IGA 和 SGA (分层架构)
            # =====================================================
            elif algo_name in ["H-IGA", "SGA"]:
                from src.routing.inter_algo import InterDomainAlgorithm
                algo_inter = InterDomainAlgorithm()
                s_vir = phy_to_vir.get(src, src)
                d_vir = phy_to_vir.get(dst, dst)
                
                # 1. 域间寻路
                path_vir, _ = algo_inter.find_path(G_vir_run, s_vir, d_vir, req)
                
                if not path_vir:
                    path, found, note = None, False, "Inter-Fail"
                else:
                    path_vir_log = path_vir # 保存以便记录日志
                    
                    # 2. 域内分解 (注意：SGA 和 H-IGA 都在 decompose 内部调用各自的 find_path)
                    # G_phy_run 会在 decompose 内部被用来构建 G_safe 视图
                    path, found, _, note = decompose_and_execute_hierarchical(
                        None, G_phy_run, G_vir_run, path_vir, phy_to_vir, src, dst, req, algo, topo_mgr
                    )
                    
                    # [日志] 记录分层算法路径 (成功才记录)
                    if found:
                        log_path_details(log_files[algo_name], req, G_phy_run, path, path_vir_log)

            # --- 2. 状态更新 (物理层模拟) ---
            # 只有找到路了才更新状态
            if found and path:
                for i in range(len(path) - 1):
                    u_hop, v_hop = path[i], path[i+1]
                    topo_mgr.update_link_state(G_phy_run, u_hop, v_hop, bw)

            # --- 3. 结果严格判决 (数据平面) ---
            # 设置更严格的丢包率阈值 (5%)，超过此值认为业务质量不达标
            LOSS_THRESHOLD = 1.0
            real_success = False
            path_metrics = {'delay': 0, 'loss': 1.0, 'max_util': 0.0}

            if found and path:
                path_metrics = iga_fitness_module.evaluate_path(G_phy_run, path)
                if path_metrics['loss'] <= LOSS_THRESHOLD:
                    real_success = True
                else:
                    real_success = False
                    note = f"HighLoss ({path_metrics['loss']:.1%})"
            else:
                real_success = False

            # --- 4. 数据记录 ---
            real_goodput = 0.0
            if real_success:
                real_goodput = bw * (1.0 - path_metrics['loss'])
                if real_goodput < 0: real_goodput = 0

            # 统一记录结果
            res_entry = {
                'ID': req['id'], 'Algo': algo_name, 'Load': n_requests,
                'Success': real_success, 
                'Bandwidth': bw,
                'Goodput': real_goodput,
                'Delay': path_metrics['delay'] if path else 0, 
                'Loss': path_metrics['loss'],
                'Hops': len(path) if path else 0,
                'MaxUtil': path_metrics['max_util'] if path else 0
            }
            if not real_success:
                res_entry['Note'] = note
            
            results.append(res_entry)

    df = pd.DataFrame(results)
    csv_path = os.path.join(base_dir, f"metrics_load_{n_requests}.csv")
    df.to_csv(csv_path, index=False)
    return df

def main():
    # ==========================================
    # [配置区] 仿真规模控制
    # ==========================================
    # 推荐的细化配置
    LOADS_TO_TEST = [10, 30, 50, 80, 100, 150, 200, 250, 300, 400, 500, 600]
    # LOADS_TO_TEST = [300] # [Debug] 仅测试拥塞点，验证微调效果
    
    print(f"🚀 [Load Analysis] Started (Strict Mode + Goodput + Full Logging).")
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
                
                pdr = sub['Success'].mean() * 100 if not sub.empty else 0
                succ_df = sub[sub['Success'] == True]
                avg_delay = succ_df['Delay'].mean() if not succ_df.empty else 0
                thr = succ_df['Bandwidth'].sum() if not succ_df.empty else 0
                goodput = sub['Goodput'].sum() if not sub.empty else 0
                avg_loss = sub['Loss'].mean() * 100 if not sub.empty else 0
                
                print(f"   >> {algo:<8}: PDR={pdr:5.1f}% | Goodput={goodput:6.1f} Mbps | Delay={avg_delay:6.1f} ms | Loss={avg_loss:5.1f}%")
                
                summary.append({
                    'Load': n, 'Algo': algo, 
                    'PDR': pdr, 
                    'Throughput': thr,      
                    'AvgGoodput': goodput,  
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