import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re
import json
import glob
from pathlib import Path

# ================== 配置 ==================
LOGS_ROOT = r"F:\HeteroSat_Routing_Sim\sim_script\logs"
TRAFFIC_CACHE_DIR = r"F:\HeteroSat_Routing_Sim\sim_script\data\traffic_cache_load_analysis"
PLOT_OUTPUT = r"F:\HeteroSat_Routing_Sim\plot\Load_Sensitivity_Traffic_Volume.png"
# ==========================================

def find_latest_load_analysis_dir(logs_root):
    """查找 logs_root 下最新的 load_analysis_YYYYMMDD_HHMMSS 目录"""
    if not os.path.exists(logs_root):
        raise FileNotFoundError(f"Logs root not found: {logs_root}")
    
    pattern = re.compile(r"^load_analysis_\d{8}_\d{6}$")
    candidate_dirs = [
        os.path.join(logs_root, d)
        for d in os.listdir(logs_root)
        if os.path.isdir(os.path.join(logs_root, d)) and pattern.match(d)
    ]
    
    if not candidate_dirs:
        raise FileNotFoundError("No load_analysis_* directory found.")
    
    # 按修改时间取最新
    latest_dir = max(candidate_dirs, key=os.path.getmtime)
    
    return latest_dir

def calculate_total_bandwidth(n_flows, traffic_dir):
    """
    根据业务数量 N 计算该批次流量的总带宽 (Mbps)
    寻找匹配 requests_T*_N{n_flows}.json 的文件
    """
    # 模式匹配: requests_T*_N{n_flows}.json
    pattern = os.path.join(traffic_dir, f"requests_T*_N{n_flows}.json")
    files = glob.glob(pattern)
    
    if not files:
        print(f"⚠️ Warning: Traffic file for N={n_flows} not found in {traffic_dir}. Assuming 0 Mbps.")
        return 0.0
    
    # 如果有多个 (理论上不应该，除非T不同)，取第一个
    target_file = files[0]
    
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # 累加所有请求的 bandwidth 字段
            total_bw = sum(req.get('bandwidth', 0) for req in data)
            return total_bw
    except Exception as e:
        print(f"❌ Error reading {target_file}: {e}")
        return 0.0

def plot_traffic_sensitivity(df, save_path):
    """绘制三指标 vs TotalTraffic 曲线"""
    sns.set_theme(style="whitegrid", font_scale=1.2)
    fig, axes = plt.subplots(3, 1, figsize=(9, 12), sharex=True)

    metrics = [
        ("AvgGoodput", "AvgGoodput (Mbps)", "(a) AvgGoodput vs Traffic Volume"),
        ("AvgDelay", "Average Delay (ms)", "(b) Average End-to-End Delay vs Traffic Volume"),
        ("AvgLoss", "Average Loss (%)", "(c) Average Packet Loss vs Traffic Volume")
    ]

    # 确保 Loss 显示为百分比 (如果是 0-1 小数)
    # 假设 summary_all_loads.csv 里的 AvgLoss 已经是百分比 (0-100) 或者小数
    # 根据 run_load_analysis.py: AvgLoss = sub['Loss'].mean() * 100，所以是 0-100
    
    for ax, (col, ylabel, title) in zip(axes, metrics):
        sns.lineplot(
            data=df,
            x="TotalTraffic",
            y=col,
            hue="Algo",
            style="Algo",
            markers=True,
            dashes=False,
            linewidth=2.5,
            markersize=9,
            palette="tab10",
            ax=ax
        )
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=13)
        if ax == axes[-1]:
            ax.set_xlabel("Total Network Traffic Demand (Mbps)")
        else:
            ax.set_xlabel("")

        # 优化图例位置
        ax.legend(title="Algorithm", loc='best')

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"✅ 图像已保存至: {save_path}")
    # plt.show() # 批处理模式下通常不显示窗口

def main():
    # 1. 找到最新的 load_analysis 目录
    try:
        latest_dir = find_latest_load_analysis_dir(LOGS_ROOT)
        print(f"✅ 使用负载分析目录: {os.path.basename(latest_dir)}")
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return

    # 2. 读取 summary_all_loads.csv
    csv_path = os.path.join(latest_dir, "summary_all_loads.csv")
    if not os.path.exists(csv_path):
        print(f"❌ Error: summary_all_loads.csv not found in {latest_dir}")
        return
    
    df = pd.read_csv(csv_path)
    print("📊 原始数据预览:")
    print(df.head())

    # 3. 计算总带宽并映射到 DataFrame
    # 获取唯一的 Load 值，避免重复读取文件
    unique_loads = df['Load'].unique()
    load_to_bw = {}
    
    print("\n🔄 正在计算各负载点的总带宽...")
    for n in unique_loads:
        bw = calculate_total_bandwidth(n, TRAFFIC_CACHE_DIR)
        load_to_bw[n] = bw
        print(f"   - Load N={n} -> Total BW = {bw:.1f} Mbps")
    
    # 映射回 DataFrame
    df['TotalTraffic'] = df['Load'].map(load_to_bw)
    
    # 按总带宽排序，确保画图连线正确
    df = df.sort_values(by='TotalTraffic')

    print("\n📊 映射后数据预览:")
    print(df[['Load', 'TotalTraffic', 'Algo', 'AvgGoodput']].head())

    # 4. 绘图
    plot_traffic_sensitivity(df, PLOT_OUTPUT)

if __name__ == "__main__":
    main()
