import pandas as pd
import matplotlib.pyplot as plt
import os
import glob
import numpy as np

def plot_sensitivity_analysis(log_dir):
    # 1. 查找目录下所有的 metrics_higa_gamma_*.csv 文件
    csv_files = glob.glob(os.path.join(log_dir, "metrics_higa_gamma_*.csv"))
    if not csv_files:
        print(f"No CSV files found in {log_dir}")
        return

    all_data = []
    for f in csv_files:
        df = pd.read_csv(f)
        all_data.append(df)
    
    full_df = pd.concat(all_data, ignore_index=True)
    
    # 2. 按 Gamma 分组统计
    # 我们主要关注 Remote_Sensing 业务，因为它是带宽密集型，对拥塞最敏感
    rs_df = full_df[full_df['Type'] == 'Remote_Sensing'].copy()
    
    # 统计指标：成功率、平均时延、平均丢包率、平均跳数、平均最大利用率
    stats = rs_df.groupby('Gamma').agg({
        'Success': 'mean',
        'Delay': 'mean',
        'Loss': 'mean',
        'Hops': 'mean',
        'MaxUtil': 'mean'
    }).reset_index()
    
    stats['SuccessRate'] = stats['Success'] * 100
    stats = stats.sort_values('Gamma')
    
    print("--- Sensitivity Analysis Stats (Remote_Sensing) ---")
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(stats)

    # 3. 绘图
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    plt.subplots_adjust(hspace=0.3, wspace=0.25)
    
    # 图1: 成功率与丢包率 (双轴)
    ax1 = axes[0, 0]
    ax1.plot(stats['Gamma'], stats['SuccessRate'], color='tab:green', marker='o', linewidth=2, label='Success Rate (%)')
    ax1.set_xlabel('Gamma (Congestion Sensitivity)')
    ax1.set_ylabel('Success Rate (%)', color='tab:green')
    ax1.tick_params(axis='y', labelcolor='tab:green')
    ax1.grid(True, linestyle='--', alpha=0.6)
    
    ax1_twin = ax1.twinx()
    ax1_twin.plot(stats['Gamma'], stats['Loss'], color='tab:red', marker='s', linewidth=2, linestyle='--', label='Avg Loss Rate')
    ax1_twin.set_ylabel('Avg Loss Rate', color='tab:red')
    ax1_twin.tick_params(axis='y', labelcolor='tab:red')
    ax1.set_title('Success Rate vs Avg Loss Rate')

    # 图2: 平均时延
    ax2 = axes[0, 1]
    ax2.plot(stats['Gamma'], stats['Delay'], color='tab:blue', marker='^', linewidth=2)
    ax2.set_xlabel('Gamma')
    ax2.set_ylabel('Avg Delay (ms)')
    ax2.set_title('Average End-to-End Delay')
    ax2.grid(True, linestyle='--', alpha=0.6)

    # 图3: 最大链路利用率 (MaxUtil)
    ax3 = axes[1, 0]
    ax3.plot(stats['Gamma'], stats['MaxUtil'], color='tab:orange', marker='d', linewidth=2)
    ax3.axhline(y=1.0, color='red', linestyle=':', label='Capacity Limit')
    ax3.set_xlabel('Gamma')
    ax3.set_ylabel('Avg Max Link Utilization')
    ax3.set_title('Link Congestion Level (MaxUtil)')
    ax3.legend()
    ax3.grid(True, linestyle='--', alpha=0.6)

    # 图4: 平均跳数
    ax4 = axes[1, 1]
    ax4.plot(stats['Gamma'], stats['Hops'], color='tab:purple', marker='v', linewidth=2)
    ax4.set_xlabel('Gamma')
    ax4.set_ylabel('Avg Hops')
    ax4.set_title('Average Path Hops')
    ax4.grid(True, linestyle='--', alpha=0.6)

    plt.suptitle(f'H-IGA Sensitivity Analysis (Traffic: Remote_Sensing)\nLog Dir: {os.path.basename(log_dir)}', fontsize=16)
    
    save_path = os.path.join(log_dir, "sensitivity_detailed_plots.png")
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"\nPlots saved to: {save_path}")
    
    # 4. 打印总体结论建议
    best_gamma = stats.loc[stats['Loss'].idxmin(), 'Gamma']
    print(f"\n[Recommendation] Based on Loss Rate, the best Gamma is around: {best_gamma}")

if __name__ == "__main__":
    target_dir = r"f:\HeteroSat_Routing_Sim\sim_script\logs\sensitivity_analysis_20260111_175448"
    plot_sensitivity_analysis(target_dir)
