# -*- coding: utf-8 -*-
"""
File: sim_script/run_sensitivity.py
Description: H-IGA 全维灵敏度分析脚本 (负载 x 拥塞敏感度)
功能: 双重扫描 (Traffic Load x Gamma)，分析不同负载下 Gamma 参数的最佳取值范围。
架构: 结果按负载分目录存储，并生成全局汇总报表。
"""
import sys
import os
import time
import pandas as pd
import logging
from tqdm import tqdm
import importlib

# 添加项目根目录
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.topology import TopologyManager
from src.traffic import TrafficGenerator
from src.utils import get_logger, SESSION_DIR
from src.routing.hierarchical_mapper import VirtualTopologyManager 
from src.simulation_utils import (
    manage_traffic, 
    decompose_and_execute_hierarchical, 
    get_sim_config,
    ensure_dir
)

# 引入 IGA 及其依赖模块
from src.routing.iga.iga import IGAStrategy
import src.routing.iga.iga_fitness as iga_fitness_module

def run_experiment_with_gamma(gamma_val, req_count, topo_mgr, traffic_gen, vtm, output_dir):
    """
    运行单次实验 (特定 Gamma + 特定负载)
    Args:
        gamma_val: 拥塞敏感度因子
        req_count: 当前负载 (请求数量)
        output_dir: 结果保存的子目录 (例如 .../Load_10/)
    """
    # -----------------------------------------------------
    # 1. 动态注入 Gamma 参数
    # -----------------------------------------------------
    iga_fitness_module.GAMMA = gamma_val
    # print(f"   🧪 Gamma={gamma_val} | Load={req_count}")
    
    # 初始化算法
    algo = IGAStrategy()
    algo_name = f"H-IGA-Gamma{gamma_val}"
    
    # 2. 配置环境
    cfg = get_sim_config()
    # SIM_DURATION = cfg['SIM_DURATION']
    # TIME_STEP = cfg['TIME_STEP']
    SIM_DURATION = 300 # 跑300s这个时间片
    TIME_STEP = cfg['TIME_STEP']
    
    results = []
    
    # 3. 仿真循环
    for t in range(SIM_DURATION, SIM_DURATION+1, TIME_STEP):
        # A. 获取物理图 & 虚拟拓扑
        G_phy = topo_mgr.get_graph_at_time(t)
        G_vir, phy_to_vir = vtm.build_virtual_graph(G_phy)
        
        # B. 加载流量 (注意：这里使用传入的 req_count)
        # 流量文件会自动命名为 requests_T{t}_N{req_count}.json，不会冲突
        # traffic_dir = os.path.join("data", "traffic_cache_sensitivity")
        traffic_dir = os.path.join("data", "traffic_cache_load_analysis") # 用和全局业务量分析一样的业务流
        requests = manage_traffic(traffic_gen, G_phy, t, req_count, traffic_dir)
        
        # C. 批量处理业务
        # 使用 leave=False 让进度条跑完就消失，保持控制台整洁
        for req in tqdm(requests, desc=f"     [Sim] T={t}", leave=False):
            src, dst = req['src'], req['dst']
            
            # 域间路由 (GEO)
            from src.routing.inter_algo import InterDomainAlgorithm
            algo_inter = InterDomainAlgorithm()
            
            s_vir = phy_to_vir.get(src, src)
            d_vir = phy_to_vir.get(dst, dst)
            path_vir, _ = algo_inter.find_path(G_vir, s_vir, d_vir, req)
            
            if not path_vir:
                results.append({
                    'ID': req['id'], 'Type': req['service_type'], 
                    'Algo': algo_name, 'Gamma': gamma_val, 'Load': req_count,
                    'Success': False, 'Note': 'Inter-Domain Fail'
                })
                continue
                
            # 域内协同 (IGA)
            full_path, success, logs, note = decompose_and_execute_hierarchical(
                None, G_phy, G_vir, path_vir, phy_to_vir, src, dst, req, algo, topo_mgr
            )
            
            # 记录结果
            if success:
                m = iga_fitness_module.evaluate_path(G_phy, full_path)
                results.append({
                    'ID': req['id'], 'Type': req['service_type'], 
                    'Algo': algo_name, 'Gamma': gamma_val, 'Load': req_count,
                    'Success': True, 
                    'Delay': m['delay'], 'Loss': m['loss'], 
                    'Hops': len(full_path), 'MaxUtil': m['max_util']
                })
            else:
                results.append({
                    'ID': req['id'], 'Type': req['service_type'], 
                    'Algo': algo_name, 'Gamma': gamma_val, 'Load': req_count,
                    'Success': False, 'Note': note
                })

    # 4. 保存详细结果到子目录
    df = pd.DataFrame(results)
    csv_name = f"metrics_G{gamma_val}_N{req_count}.csv"
    csv_path = os.path.join(output_dir, csv_name)
    df.to_csv(csv_path, index=False)
    
    return df

def main():
    # ==========================================
    # 1. 实验参数配置
    # ==========================================
    # 负载列表 (业务数量)
    # LOAD_LIST = [10, 20, 30, 40, 50, 60, 80, 100, 120] 
    LOAD_LIST = [10, 30, 50, 80, 100, 150, 200, 250, 300, 400, 500, 600] #保持与run_load_analysis.py保持一致
    
    
    # Gamma 列表 (拥塞敏感度)
    GAMMAS_TO_TEST = [
        1.0, 2.0, 3.0, 4.0, 5.0, 
        6.0, 7.0, 8.0, 9.0, 10.0, 
        11.0, 12.0, 13.0, 14.0, 15.0
    ]
    
    # 创建主 Session 目录
    session_time = time.strftime("%Y%m%d_%H%M%S")
    base_dir = os.path.join("logs", f"sensitivity_full_{session_time}")
    ensure_dir(base_dir)
    
    print(f"🚀 [Full Sensitivity Analysis] Started.")
    print(f"📂 Master Session Directory: {base_dir}")
    print(f"📊 Loads: {LOAD_LIST}")
    print(f"🎚️ Gammas: {GAMMAS_TO_TEST}")
    
    # ==========================================
    # 2. 初始化共享组件 (只初始化一次，提高效率)
    # ==========================================
    topo_mgr = TopologyManager()
    traffic_gen = TrafficGenerator(topo_mgr)
    vtm = VirtualTopologyManager()
    
    grand_summary = [] # 用于存储全局汇总数据
    
    # ==========================================
    # 3. 双层循环遍历
    # ==========================================
    total_experiments = len(LOAD_LIST) * len(GAMMAS_TO_TEST)
    pbar = tqdm(total=total_experiments, desc="Total Progress")
    
    for req_count in LOAD_LIST:
        # 为每个负载创建一个子目录 (如 Load_010)
        load_subdir = os.path.join(base_dir, f"Load_{req_count:03d}")
        ensure_dir(load_subdir)
        
        print(f"\n📥 [Load Level] Processing Request Count: {req_count}")
        
        for gamma in GAMMAS_TO_TEST:
            # 运行单次实验
            df = run_experiment_with_gamma(
                gamma, req_count, topo_mgr, traffic_gen, vtm, load_subdir
            )
            
            # 计算聚合指标
            success_rate = df['Success'].mean() * 100
            avg_delay = df[df['Success']==True]['Delay'].mean() if not df.empty else 0
            avg_hops = df[df['Success']==True]['Hops'].mean() if not df.empty else 0
            
            # 存入全局汇总
            grand_summary.append({
                'Load': req_count,
                'Gamma': gamma,
                'SuccessRate': success_rate,
                'AvgDelay': avg_delay,
                'AvgHops': avg_hops
            })
            
            pbar.update(1)
            
    pbar.close()

    # ==========================================
    # 4. 生成全局汇总报表
    # ==========================================
    summary_df = pd.DataFrame(grand_summary)
    summary_path = os.path.join(base_dir, "grand_summary.csv")
    summary_df.to_csv(summary_path, index=False)
    
    print("\n" + "="*60)
    print("✅ Full Analysis Completed!")
    print(f"📄 Grand Summary saved to: {summary_path}")
    print("="*60)
    
    # 简单打印一下每个负载下的最佳 Gamma (按成功率优先，时延次之)
    print("\n🏆 Best Gamma per Load Level:")
    for load in LOAD_LIST:
        subset = summary_df[summary_df['Load'] == load]
        if not subset.empty:
            # 排序逻辑: 成功率降序 -> 时延升序
            best = subset.sort_values(by=['SuccessRate', 'AvgDelay'], ascending=[False, True]).iloc[0]
            print(f"   Load {load:3d}: Best Gamma = {best['Gamma']:4.1f} "
                  f"(Succ: {best['SuccessRate']:5.1f}%, Delay: {best['AvgDelay']:6.1f}ms)")

if __name__ == '__main__':
    main()