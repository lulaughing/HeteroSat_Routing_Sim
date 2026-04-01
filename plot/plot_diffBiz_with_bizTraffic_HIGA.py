import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re
import json
import glob
from pathlib import Path

# ================== 配置 ==================
# LOGS_ROOT = r"F:\HeteroSat_Routing_Sim\sim_script\logs"
LOGS_ROOT = r"F:\HeteroSat_Routing_Sim\logs"
TRAFFIC_CACHE_DIR = r"F:\HeteroSat_Routing_Sim\sim_script\data\traffic_cache_load_analysis"
PLOT_OUTPUT = r"F:\HeteroSat_Routing_Sim\plot\Load_Sensitivity_DiffBiz_Traffic_HIGA.png"
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
    
    latest_dir = max(candidate_dirs, key=os.path.getmtime)
    return latest_dir

def get_traffic_info(n_flows, traffic_dir):
    """
    获取指定 N 下的：
    1. 总带宽 (Total Traffic)
    2. ID -> ServiceType 的映射字典
    """
    pattern = os.path.join(traffic_dir, f"requests_T*_N{n_flows}.json")
    files = glob.glob(pattern)
    
    if not files:
        print(f"⚠️ Warning: Traffic file for N={n_flows} not found. Skipping.")
        return 0.0, {}
    
    target_file = files[0]
    id_map = {}
    total_bw = 0.0
    
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for req in data:
                req_id = req.get('id')
                s_type = req.get('service_type', 'Unknown')
                bw = req.get('bandwidth', 0)
                
                id_map[req_id] = s_type
                total_bw += bw
                
        return total_bw, id_map
    except Exception as e:
        print(f"❌ Error reading {target_file}: {e}")
        return 0.0, {}

def process_metrics(latest_dir):
    """读取所有 metrics csv 并聚合数据"""
    all_data = []
    
    # 查找所有 metrics_load_*.csv
    csv_files = glob.glob(os.path.join(latest_dir, "metrics_load_*.csv"))
    
    print(f"🔍 Found {len(csv_files)} metrics files.")
    
    for csv_file in csv_files:
        # 提取 N
        match = re.search(r"metrics_load_(\d+)\.csv", csv_file)
        if not match: continue
        n_load = int(match.group(1))
        
        # 1. 获取流量信息
        total_traffic, id_map = get_traffic_info(n_load, TRAFFIC_CACHE_DIR)
        if not id_map: continue
        
        # 2. 读取 CSV
        try:
            df = pd.read_csv(csv_file)
        except Exception as e:
            print(f"❌ Error reading {csv_file}: {e}")
            continue
            
        # 3. 筛选 H-IGA
        df = df[df['Algo'] == 'H-IGA'].copy()
        if df.empty: continue
        
        # 4. 映射 Service Type
        df['Type'] = df['ID'].map(id_map)
        
        # 5. 按 Type 分组计算指标
        # AvgDelay: 成功传输的平均时延
        # AvgLoss: 平均丢包率
        # AvgGoodput: 该类业务所有流的 Goodput 之和 (反映系统对该业务的总产出)
        # 或者使用 mean (反映单流平均体验)。考虑到 RemoteSensing 和 Voice 带宽差异巨大，sum 不可比。
        # 但如果是“有效吞吐量”，通常指系统容量。
        # 让我们计算 SUM Goodput，因为这对 Remote Sensing 才有意义。
        # 对比时，我们可以看趋势。
        
        grouped = df.groupby('Type')
        
        for s_type, group in grouped:
            # 成功流统计
            success_group = group[group['Success'] == True]
            
            avg_delay = success_group['Delay'].mean() if not success_group.empty else 0
            avg_loss = group['Loss'].mean() * 100 # 转百分比
            
            # Goodput: 使用 SUM (该业务类型的总有效产出)
            # 这样可以看到随着负载增加，系统处理各类业务的总吞吐量都在上升
            total_goodput = group['Goodput'].sum()
            
            all_data.append({
                'TotalTraffic': total_traffic,
                'Load': n_load,
                'ServiceType': s_type,
                'AvgDelay': avg_delay,
                'AvgLoss': avg_loss,
                'TotalGoodput': total_goodput
            })
            
    return pd.DataFrame(all_data)

def plot_biz_sensitivity(df, save_path):
    """绘制不同业务的指标曲线"""
    sns.set_theme(style="whitegrid", font_scale=1.2)
    fig, axes = plt.subplots(3, 1, figsize=(10, 14), sharex=True)

    metrics = [
        ("TotalGoodput", "Total Goodput (Mbps)", "(a) Total Goodput vs Traffic Volume (H-IGA)"),
        ("AvgDelay", "Average Delay (ms)", "(b) Average End-to-End Delay vs Traffic Volume (H-IGA)"),
        ("AvgLoss", "Average Loss (%)", "(c) Average Packet Loss vs Traffic Volume (H-IGA)")
    ]
    
    # 排序以保证连线顺滑
    df = df.sort_values(by='TotalTraffic')

    for ax, (col, ylabel, title) in zip(axes, metrics):
        sns.lineplot(
            data=df,
            x="TotalTraffic",
            y=col,
            hue="ServiceType",
            style="ServiceType",
            markers=True,
            dashes=False,
            linewidth=2.5,
            markersize=9,
            palette="Set2", # 使用不同的配色
            ax=ax
        )
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontsize=13)
        if ax == axes[-1]:
            ax.set_xlabel("Total Network Traffic Demand (Mbps)")
        else:
            ax.set_xlabel("")

        ax.legend(title="Service Type", loc='best')

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"✅ 图像已保存至: {save_path}")

def main():
    # 1. 找到最新目录
    try:
        latest_dir = find_latest_load_analysis_dir(LOGS_ROOT)
        print(f"✅ 使用负载分析目录: {os.path.basename(latest_dir)}")
    except FileNotFoundError as e:
        print(f"❌ Error: {e}")
        return

    # 2. 处理数据
    print("🔄 正在聚合数据...")
    df = process_metrics(latest_dir)
    
    if df.empty:
        print("❌ No data found or processing failed.")
        return
        
    print("📊 数据预览:")
    print(df.head())
    
    # 3. 保存处理后的数据
    out_dir = r"F:\HeteroSat_Routing_Sim\data\results\BizQoS"
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    csv_out = os.path.join(out_dir, "H-IGA_BizQoS_vs_Traffic.csv")
    df.to_csv(csv_out, index=False)
    print(f"✅ 处理后的数据已保存至: {csv_out}")
    
    # 4. 绘图
    plot_biz_sensitivity(df, PLOT_OUTPUT)

if __name__ == "__main__":
    main()
