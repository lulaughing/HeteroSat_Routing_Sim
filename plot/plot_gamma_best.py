import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import glob

# ================= 配置区域 =================
# 设置你的日志根目录
BASE_DIR = Path(r"F:\HeteroSat_Routing_Sim\sim_script\logs")
OUTPUT_DIR = Path(r"F:\HeteroSat_Routing_Sim\plot")


# 定义不同负载对应的文件夹名称
# num_of_bizs_list = [10, 20, 30, 40, 50, 60, 80, 100, 120]
num_of_bizs_list = [10, 30, 50, 80, 100, 150, 200, 250, 300, 400, 500, 600] #保持与run_load_analysis.py保持一致

# 匹配所有 sensitivity_full_* 目录，按时间戳取最新
pattern = BASE_DIR / "sensitivity_full_*"
dirs = sorted(glob.glob(str(pattern)))  # 按字典序 ≈ 时间序
if not dirs:
    raise FileNotFoundError(f"未找到任何目录")
latest_dir = dirs[-1]  # 最后 = 最新
TARGET_DIRS = {f'Load_{load}': os.path.join(latest_dir, f'Load_{load:03d}') for load in num_of_bizs_list}

# 输出图片文件名
IMG_FILENAME = "Gamma_Sensitivity_Dual_Metrics.png"
# 输出数据文件名
CSV_FILENAME = "summary.csv"
# ===========================================


def parse_simulation_logs(base_dir, target_dirs):
    data_list = []

    for label, dir_name in target_dirs.items():
        if not os.path.exists(dir_name):
            print(f"Warning: Directory not found: {dir_name}")
            continue

        print(f"Processing {label} in {dir_name}...")

        for file in os.listdir(dir_name):
            if file.startswith("metrics_G") and file.endswith(".csv"):
                try:
                    file_path = os.path.join(dir_name, file)

                    # === 修复：正确提取 Gamma 值 ===
                    # 文件名如: metrics_G1.0_N10.csv
                    # 使用正则提取数字部分
                    import re
                    match = re.search(r'metrics_G([\d.]+)_N\d+\.csv', file)
                    if not match:
                        print(f"跳过无法解析 Gamma 的文件: {file}")
                        continue
                    gamma_val = float(match.group(1))

                    # 读取 CSV
                    df = pd.read_csv(file_path)

                    # 成功率处理
                    if 'Success' in df.columns:
                        df['Success'] = df['Success'].astype(str).str.strip().str.lower() == 'true'
                        df_success = df[df['Success']]
                    else:
                        df_success = df

                    if len(df_success) == 0:
                        continue

                    avg_delay = df_success['Delay'].mean()
                    avg_max_util = df_success['MaxUtil'].mean()
                    success_rate = len(df_success) / len(df) * 100

                    load_num = int(label.replace('Load_', ''))

                    data_list.append({
                        "Traffic Load": load_num,
                        "Gamma": gamma_val,
                        "Avg Delay (ms)": avg_delay,
                        "Avg Bottleneck Util": avg_max_util,
                        "Success Rate (%)": success_rate
                    })

                except Exception as e:
                    print(f"Error processing {file}: {e}")

    df_res = pd.DataFrame(data_list)
    if not df_res.empty:
        df_res = df_res.sort_values(by=["Traffic Load", "Gamma"])
    return df_res


def save_summary_csv(df, path):
    """
    保存处理好的数据到 CSV
    """
    if df.empty:
        return
    df.to_csv(path, index=False)
    print(f"\n[Success] Summary data saved to: {path}")

def plot_dual_metrics(df):
    """
    绘制双子图：上方时延，下方利用率
    """
    if df.empty:
        print("No data found to plot!")
        return

    # [优化 1] 确保输出目录存在
    save_dir = OUTPUT_DIR / "gamma"
    save_dir.mkdir(parents=True, exist_ok=True)

    # [优化 2] 将负载转为分类变量，保证图例清晰
    # 这样 Seaborn 会为每条线生成独立的图例项，而不是渐变色条
    plot_data = df.copy()
    plot_data["Traffic Load"] = plot_data["Traffic Load"].astype(str)
    
    # 自定义排序，防止字符串排序导致的 '10', '100', '20' 问题
    # 按照数值大小重新排序 DataFrame，Seaborn 会遵循这个顺序
    plot_data["_load_int"] = plot_data["Traffic Load"].astype(int)
    plot_data = plot_data.sort_values(by=["_load_int", "Gamma"])

    # 设置绘图风格
    sns.set_theme(style="whitegrid", font_scale=1.1)
    
    # 创建 2 行 1 列的子图，共享 X 轴
    fig, axes = plt.subplots(2, 1, figsize=(10, 12), sharex=True) # 稍微拉长一点高度

    # 定义颜色盘 (使用 distinct 的颜色，或者 rocket/viridis)
    palette = "viridis"

    # --- 子图 1: 平均时延 ---
    sns.lineplot(
        data=plot_data, x="Gamma", y="Avg Delay (ms)", hue="Traffic Load", style="Traffic Load",
        markers=True, dashes=False, linewidth=2.5, markersize=8, palette=palette,
        ax=axes[0]
    )
    axes[0].set_title("(a) Impact on Average End-to-End Delay", fontsize=14, fontweight='bold')
    axes[0].set_ylabel("Avg Delay (ms)")
    # 优化图例位置，移到图外以免遮挡数据
    axes[0].legend(bbox_to_anchor=(1.02, 1), loc='upper left', borderaxespad=0, title="Traffic Load")

    # --- 子图 2: 平均瓶颈利用率 ---
    sns.lineplot(
        data=plot_data, x="Gamma", y="Avg Bottleneck Util", hue="Traffic Load", style="Traffic Load",
        markers=True, dashes=False, linewidth=2.5, markersize=8, palette=palette,
        ax=axes[1], legend=False # 下方不显示图例，共用上方的
    )
    axes[1].set_title("(b) Impact on Bottleneck Link Utilization", fontsize=14, fontweight='bold')
    axes[1].set_ylabel("Avg Bottleneck Utilization")
    axes[1].set_xlabel(r"Congestion Sensitivity Factor ($\gamma$)")
    
    # 设置 X 轴刻度
    unique_gammas = sorted(df["Gamma"].unique())
    axes[1].set_xticks(unique_gammas)
    axes[1].set_xlim(min(unique_gammas)-0.5, max(unique_gammas)+0.5)

    # # [优化 3] 标记推荐值 (Gamma=10.0)
    # RECOMMENDED_GAMMA = 10.0
    # for ax in axes:
    #     # 画竖线
    #     ax.axvline(x=RECOMMENDED_GAMMA, color='#e74c3c', linestyle='--', linewidth=2, alpha=0.8)
    #     # 添加文本标注 (仅在上方图添加，避免重复)
    #     if ax == axes[0]:
    #         ax.text(RECOMMENDED_GAMMA + 0.2, ax.get_ylim()[1]*0.95, 
    #                 f'Selected $\gamma={int(RECOMMENDED_GAMMA)}$', 
    #                 color='#e74c3c', fontweight='bold', ha='left')

    plt.tight_layout()
    
    # 保存图片
    save_path = save_dir / IMG_FILENAME
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"[Success] Graph saved to: {save_path}")
    plt.show()




# ================= 主程序 =================
if __name__ == "__main__":
    # 1. 解析数据
    df_result = parse_simulation_logs(BASE_DIR, TARGET_DIRS)
    
    # 2. 保存 Summary CSV
    csv_path = OUTPUT_DIR / "gamma" / CSV_FILENAME
    save_summary_csv(df_result, csv_path)

    # 3. 打印预览
    print("\n--- Summary Data Preview ---")
    print(df_result.head())

    # 4. 绘图
    plot_dual_metrics(df_result)