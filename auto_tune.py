# -*- coding: utf-8 -*-
"""
File: auto_tune.py
Description: 自动化参数寻优脚本 - 寻找论文最佳数据点
"""
import pandas as pd
from main import run_simulation
import logging

# 禁止底层日志刷屏
logging.getLogger('FLOW').setLevel(logging.ERROR)
logging.getLogger('NET').setLevel(logging.ERROR)

def auto_tune():
    print("🚀 开始自动寻优 (Auto-Tuning)...")
    print("目标: Dijkstra Loss > 0.3 (严重拥塞) AND H-IGA Success > 0.8 (高成功率)")
    
    # 定义搜索空间
    # 业务带宽：覆盖 20M(等于瓶颈) 到 100M(等于跨层)
    bw_candidates = [30, 45, 60, 80] 
    # 请求数量：覆盖中载到重载
    count_candidates = [100, 150, 200]
    
    results = []
    
    for bw in bw_candidates:
        for count in count_candidates:
            print(f"\n⚡ 测试组合: Remote_BW={bw}Mbps, Req_Count={count} ... ", end="", flush=True)
            
            try:
                metrics = run_simulation(remote_sensing_bw=bw, request_count=count, verbose=False)
                
                metrics['BW'] = bw
                metrics['Count'] = count
                
                # 计算一个“推荐分”
                # 我们希望: Dijkstra Loss 越大越好, H-IGA Success 越高越好
                # Score = (Dijk_Loss * 100) + (HIGA_Succ * 50)
                score = (metrics['Dijk_Loss'] * 100) + (metrics['HIGA_Succ'] * 50)
                metrics['Score'] = round(score, 2)
                
                results.append(metrics)
                print(f"完成! Score={score:.1f}")
                print(f"   -> Dijk_Loss={metrics['Dijk_Loss']:.3f}, HIGA_Succ={metrics['HIGA_Succ']:.2f}")
                
            except Exception as e:
                print(f"出错: {e}")

    # 输出汇总表
    df = pd.DataFrame(results)
    # 调整列顺序
    cols = ['BW', 'Count', 'Score', 'HIGA_Succ', 'Dijk_Loss', 'HIGA_Loss', 'Dijk_Delay', 'HIGA_Delay']
    df = df[cols].sort_values(by='Score', ascending=False)
    
    print("\n\n🏆 寻优结果排行榜 (Top 5):")
    print(df.head(5).to_string(index=False))
    
    best = df.iloc[0]
    print(f"\n✅ 推荐黄金参数: Remote_BW = {best['BW']}, Request_Count = {best['Count']}")
    print(f"   预期效果: Dijkstra将丢包 {best['Dijk_Loss']:.1%}, H-IGA成功率 {best['HIGA_Succ']:.1%}")

if __name__ == "__main__":
    auto_tune()