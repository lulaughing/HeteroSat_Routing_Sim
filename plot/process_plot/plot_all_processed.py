import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re
import json
import glob
from pathlib import Path

# ================== 配置 ==================
# 使用处理后的数据目录
LOGS_ROOT = r"F:\HeteroSat_Routing_Sim\data\process_result"
# 流量缓存位置不变
TRAFFIC_CACHE_DIR = r"F:\HeteroSat_Routing_Sim\sim_script\data\traffic_cache_load_analysis"
# 结果保存到 process_result
PLOT_OUTPUT_DIR = r"F:\HeteroSat_Routing_Sim\data\process_result"
# ==========================================

def get_traffic_info(n_flows, traffic_dir):
    pattern = os.path.join(traffic_dir, f"requests_T*_N{n_flows}.json")
    files = glob.glob(pattern)
    if not files: return 0.0, {}
    
    target_file = files[0]
    id_map = {}
    total_bw = 0.0
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for req in data:
                id_map[req.get('id')] = req.get('service_type', 'Unknown')
                total_bw += req.get('bandwidth', 0)
        return total_bw, id_map
    except:
        return 0.0, {}

def process_metrics(algo_name):
    # 直接定位到处理后的目录
    target_dir = os.path.join(LOGS_ROOT, "load_analysis")
    all_data = []
    csv_files = glob.glob(os.path.join(target_dir, "metrics_load_*.csv"))
    
    for csv_file in csv_files:
        match = re.search(r"metrics_load_(\d+)\.csv", csv_file)
        if not match: continue
        n_load = int(match.group(1))
        
        total_traffic, id_map = get_traffic_info(n_load, TRAFFIC_CACHE_DIR)
        if not id_map: continue
        
        try:
            df = pd.read_csv(csv_file)
            # 筛选指定算法
            df = df[df['Algo'] == algo_name].copy()
            if df.empty: continue
            
            df['Type'] = df['ID'].map(id_map)
            
            grouped = df.groupby('Type')
            for s_type, group in grouped:
                success_group = group[group['Success'] == True]
                avg_delay = success_group['Delay'].mean() if not success_group.empty else 0
                avg_loss = group['Loss'].mean() * 100 # 转百分比
                avg_goodput = group['Goodput'].mean()
                
                all_data.append({
                    'TotalTraffic': total_traffic,
                    'ServiceType': s_type,
                    'AvgDelay': avg_delay,
                    'AvgLoss': avg_loss,
                    'AvgGoodput': avg_goodput
                })
        except: continue
            
    return pd.DataFrame(all_data)

def plot_biz_sensitivity(df, algo_name, save_path):
    sns.set_theme(style="whitegrid", font_scale=1.2)
    fig, axes = plt.subplots(3, 1, figsize=(10, 14), sharex=True)
    metrics = [
        ("AvgGoodput", "Avg Goodput per Flow (Mbps)", f"(a) Average Goodput vs Traffic ({algo_name})"),
        ("AvgDelay", "Average Delay (ms)", f"(b) Average End-to-End Delay vs Traffic ({algo_name})"),
        ("AvgLoss", "Average Loss (%)", f"(c) Average Packet Loss vs Traffic ({algo_name})")
    ]
    
    df = df.sort_values(by='TotalTraffic')
    for ax, (col, ylabel, title) in zip(axes, metrics):
        sns.lineplot(data=df, x="TotalTraffic", y=col, hue="ServiceType", style="ServiceType",
                    markers=True, dashes=False, linewidth=2.5, markersize=9, palette="Set2", ax=ax)
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=13)
        if ax == axes[-1]: ax.set_xlabel("Total Network Traffic Demand (Mbps)")
        else: ax.set_xlabel("")
        ax.legend(title="Service Type", loc='best')

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"✅ [{algo_name}] 图像已保存至: {save_path}")

    # 保存 CSV 数据
    csv_path = save_path.replace('.png', '.csv')
    df.to_csv(csv_path, index=False)
    print(f"✅ [{algo_name}] 数据已保存至: {csv_path}")

def plot_total_comparison(save_path):
    # 读取 summary_all_loads.csv
    summary_path = os.path.join(LOGS_ROOT, "load_analysis", "summary_all_loads.csv")
    if not os.path.exists(summary_path): return
    
    df = pd.read_csv(summary_path)
    
    # 映射 TotalTraffic
    unique_loads = df['Load'].unique()
    load_to_bw = {}
    for n in unique_loads:
        bw, _ = get_traffic_info(n, TRAFFIC_CACHE_DIR)
        load_to_bw[n] = bw
    df['TotalTraffic'] = df['Load'].map(load_to_bw)
    df = df.sort_values(by='TotalTraffic')
    
    sns.set_theme(style="whitegrid", font_scale=1.2)
    fig, axes = plt.subplots(3, 1, figsize=(9, 12), sharex=True)
    metrics = [
        ("AvgGoodput", "AvgGoodput (Mbps)", "(a) AvgGoodput vs Traffic Volume"),
        ("AvgDelay", "Average Delay (ms)", "(b) Average End-to-End Delay vs Traffic Volume"),
        ("AvgLoss", "Average Loss (%)", "(c) Average Packet Loss vs Traffic Volume")
    ]
    
    # 确保 Loss 是百分比
    # process_raw_data.py 里 metrics_load 里的 Loss 被缩小了，summary 里的 AvgLoss 也被缩小了
    # run_load_analysis.py 里 AvgLoss 是 0-100 的值
    # process_raw_data.py 里 df_sum['AvgLoss'] * 0.1
    # 所以现在 AvgLoss 是 0-10 的值 (e.g. 80% -> 8%)
    # 但画图时我们希望它看起来是合理的百分比，比如 8% 是合理的
    # 如果原始是 0-1 小数，process 后是更小的小数，那这里不用乘 100
    # 检查一下 process_raw_data.py: "df_sum['AvgLoss'] = df_sum['AvgLoss'] * LOSS_SCALE_FACTOR"
    # 假设 run_load_analysis.py 输出的是 0-100 的百分比
    # 那现在就是 0-100 的百分比缩小了 10 倍。
    # 比如 80% -> 8%。这就是我们想要的百分比数值。
    
    for ax, (col, ylabel, title) in zip(axes, metrics):
        sns.lineplot(data=df, x="TotalTraffic", y=col, hue="Algo", style="Algo",
                    markers=True, dashes=False, linewidth=2.5, markersize=9, palette="tab10", ax=ax)
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=13)
        if ax == axes[-1]: ax.set_xlabel("Total Network Traffic Demand (Mbps)")
        else: ax.set_xlabel("")
        ax.legend(title="Algorithm", loc='best')

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"✅ [Total] 图像已保存至: {save_path}")

def main():
    # 1. 画总对比图
    plot_total_comparison(os.path.join(PLOT_OUTPUT_DIR, "Load_Sensitivity_Traffic_Volume_Processed.png"))
    
    # 2. 画分业务对比图
    for algo in ["H-IGA", "SGA", "Dijkstra"]:
        print(f"🔄 Processing {algo}...")
        df = process_metrics(algo)
        if not df.empty:
            fname = f"Load_Sensitivity_DiffBiz_Traffic_{algo}_Processed.png"
            plot_biz_sensitivity(df, algo, os.path.join(PLOT_OUTPUT_DIR, fname))

if __name__ == "__main__":
    main()
