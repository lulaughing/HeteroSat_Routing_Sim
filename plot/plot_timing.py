import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re
from pathlib import Path

# ================== 配置 ==================
LOGS_ROOT = r"F:\HeteroSat_Routing_Sim\sim_script\logs"
PLOT_OUTPUT = r"F:\HeteroSat_Routing_Sim\plot\Load_Sensitivity_Comparison.png"
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
    print(f"✅ 使用最新负载分析目录: {os.path.basename(latest_dir)}")
    return latest_dir

def plot_load_sensitivity(df, save_path):
    """绘制三指标 vs Load 曲线"""
    sns.set_theme(style="whitegrid", font_scale=1.2)
    fig, axes = plt.subplots(3, 1, figsize=(9, 12), sharex=True)

    metrics = [
        ("AvgGoodput", "AvgGoodput (Mbps)", "(a) AvgGoodput vs Load"),
        ("AvgDelay", "Average Delay (ms)", "(b) Average End-to-End Delay vs Load"),
        ("AvgLoss", "Average Loss (packets)", "(c) Average Packet Loss vs Load")
    ]

    for ax, (col, ylabel, title) in zip(axes, metrics):
        sns.lineplot(
            data=df,
            x="Load",
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
            ax.set_xlabel("Network Load (Number of Flows)")
        else:
            ax.set_xlabel("")

        # 优化图例位置
        ax.legend(title="Algorithm", loc='best')

    plt.tight_layout()
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"✅ 图像已保存至: {save_path}")
    plt.show()

def main():
    # 1. 找到最新的 load_analysis 目录
    latest_dir = find_latest_load_analysis_dir(LOGS_ROOT)
    
    # 2. 读取 summary_all_loads.csv
    csv_path = os.path.join(latest_dir, "summary_all_loads.csv")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"summary_all_loads.csv not found in {latest_dir}")
    
    df = pd.read_csv(csv_path)
    print("📊 数据预览:")
    print(df.head())

    # 3. 绘图
    plot_load_sensitivity(df, PLOT_OUTPUT)

if __name__ == "__main__":
    main()