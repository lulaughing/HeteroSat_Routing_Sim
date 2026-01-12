# -*- coding: utf-8 -*-
"""
File: sim_script/plot_sensitivity_util.py
Description: 灵敏度分析 (利用率 vs 时延) 
"""
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
import glob
import re

# =================配置区域=================
sns.set(style="whitegrid", context="paper", font_scale=1.4)
plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False
# =========================================

num_of_bizs = 60  # 👈 修改这里指定业务量规模
# 1. 筛选核心业务
target_type = 'Remote_Sensing'
# target_type = ''

def find_latest_log_dir(num_of_bizs):
    """
    根据 num_of_bizs 查找最新的 sensitivity_analysis_..._N{num_of_bizs} 目录
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_dir)
    candidate_paths = [
        os.path.join(current_dir, "logs"),
        os.path.join(root_dir, "logs"),
        os.path.join(current_dir, "sensitivity_analysis"),
    ]
    
    pattern = re.compile(rf"sensitivity_analysis.*_N{num_of_bizs}$")
    found_dirs = []
    
    for base_path in candidate_paths:
        if os.path.exists(base_path):
            for item in os.listdir(base_path):
                full_path = os.path.join(base_path, item)
                if os.path.isdir(full_path) and pattern.search(item):
                    found_dirs.append(full_path)
    
    if not found_dirs:
        print(f"⚠️ 未找到匹配 N{num_of_bizs} 的日志目录")
        return None
        
    # 按修改时间排序，取最新
    found_dirs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
    latest_dir = found_dirs[0]
    print(f"✅ [System] 锁定日志目录 (N{num_of_bizs}): {latest_dir}")
    return latest_dir

def load_data(log_dir):
    all_files = glob.glob(os.path.join(log_dir, "metrics_higa_gamma_*.csv"))
    if not all_files: 
        return pd.DataFrame()
    df_list = []
    for f in all_files:
        try:
            temp_df = pd.read_csv(f)
            if 'Gamma' not in temp_df.columns:
                try: 
                    temp_df['Gamma'] = float(f.split('gamma_')[-1].replace('.csv', ''))
                except: 
                    pass
            df_list.append(temp_df)
        except Exception as e:
            print(f"⚠️ 跳过文件 {f}: {e}")
            pass
    return pd.concat(df_list, ignore_index=True) if df_list else pd.DataFrame()

def plot_sensitivity_util(df, output_dir):
    
    plot_df = df[df['Type'] == target_type]
    
    if plot_df.empty:
        plot_df = df
        title_suffix = "All Traffic"
    else:
        title_suffix = f"{target_type}"

    # 2. 计算统计值
    stats = plot_df.groupby('Gamma').apply(
        lambda x: pd.Series({
            'AvgMaxUtil': x['MaxUtil'].mean(),
            'AvgDelay': x[x['Success']==True]['Delay'].mean()
        })
    ).reset_index().sort_values('Gamma')

    print("\n📊 [Stats] 利用率 vs 时延数据:")
    print(stats)

    # 3. 绘图
    fig, ax1 = plt.subplots(figsize=(10, 6))

    # --- 左轴：瓶颈链路利用率 ---
    color_util = '#FF7F0E'
    ax1.set_xlabel(r'Congestion Sensitivity ($\gamma$)', fontsize=14, fontweight='bold')
    ax1.set_ylabel('Avg Bottleneck Utilization (Ratio)', color=color_util, fontsize=14, fontweight='bold')
    l1, = ax1.plot(stats['Gamma'], stats['AvgMaxUtil'], color=color_util, marker='^',
                   linewidth=3, markersize=12, label='Link Utilization')
    ax1.tick_params(axis='y', labelcolor=color_util, labelsize=12)
    ax1.grid(True, linestyle='--', alpha=0.5)
    # ax1.set_ylim(0, 1.1) 

    # --- 右轴：时延 ---
    ax2 = ax1.twinx()
    color_delay = '#1F77B4'
    ax2.set_ylabel('Avg End-to-End Delay (ms)', color=color_delay, fontsize=14, fontweight='bold')
    l2, = ax2.plot(stats['Gamma'], stats['AvgDelay'], color=color_delay, marker='s',
                   linestyle='--', linewidth=3, markersize=10, label='Avg Delay')
    ax2.tick_params(axis='y', labelcolor=color_delay, labelsize=12)
    ax2.grid(False)

    # --- 标题与图例 ---
    plt.title(f'Trade-off: Congestion Avoidance vs. Delay ({title_suffix}) (业务条数= {num_of_bizs})',
              fontsize=16, pad=20)

    lines = [l1, l2]
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper center',
               bbox_to_anchor=(0.5, 1.18),
               ncol=2, frameon=False, fontsize=12, columnspacing=1.2)

    # 调整布局，防止裁剪
    plt.tight_layout()
    plt.subplots_adjust(top=0.85)  # 为顶部图例留空间

    # 保存图像
    save_path = os.path.join(output_dir, f"sensitivity_util_delay_{title_suffix}.png")
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"\n✅ 图表已保存: {save_path}")
    plt.close(fig)  # 释放内存

def main():
    
    log_dir = find_latest_log_dir(num_of_bizs)
    
    if log_dir is None:
        print("❌ 未找到有效日志目录，程序退出。")
        return

    df = load_data(log_dir)
    if df.empty:
        print("❌ 加载的数据为空，无法绘图。")
        return

    plot_sensitivity_util(df, log_dir)

if __name__ == "__main__":
    main()