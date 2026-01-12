# -*- coding: utf-8 -*-
"""
File: plot_results.py
Description: 仿真结果可视化脚本
功能: 自动读取最新的仿真 CSV，绘制对比图表并保存到 plot/ 目录
"""
import os
import glob
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# =================配置区域=================
LOGS_DIR = "../logs"
BASE_OUTPUT_DIR = "../plot/"
CURRENT_SESSION_ID = "" # 动态获取
GLOBAL_REQ_COUNT = ""   # [新增] 存储业务条数用于标题
# 图表风格设置
sns.set_theme(style="whitegrid")
plt.rcParams['font.sans-serif'] = ['Arial'] # 防止中文乱码可换 ['SimHei']
plt.rcParams['axes.unicode_minus'] = False
# =========================================

def get_latest_session_dir():
    """获取 logs/ 下最新的且匹配业务条数参数的 session 目录"""
    global GLOBAL_REQ_COUNT
    if not os.path.exists(LOGS_DIR):
        print(f"❌ 找不到日志目录: {LOGS_DIR}")
        return None
    
    # 提示用户手动输入业务条数
    user_input = input(f"👉 请输入要绘图的业务条数 N (直接回车默认 300): ").strip()
    req_count = user_input if user_input else "300"
    GLOBAL_REQ_COUNT = req_count
    
    pattern = f"session_*_N{req_count}"
    
    sessions = glob.glob(os.path.join(LOGS_DIR, pattern))
    
    if not sessions:
        print(f"⚠️ 没有找到匹配 N={req_count} 的 session，尝试寻找所有 session...")
        sessions = glob.glob(os.path.join(LOGS_DIR, "session_*"))
        
    if not sessions:
        print("❌ 没有找到任何 session 记录")
        return None
    
    # 按创建时间排序，取最新的
    latest_dir = max(sessions, key=os.path.getmtime)
    print(f"📂 读取匹配数据 (N={req_count}): {latest_dir}")
    return latest_dir

def load_data(session_dir):
    """读取并合并三个算法的 CSV"""
    dfs = []
    algos = ['dijkstra', 'dijkstra_qos', 'sga', 'higa']
    
    for algo in algos:
        csv_path = os.path.join(session_dir, f"metrics_{algo}.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            # 确保 Algo 名字统一漂亮
            algo_name = "H-IGA" if algo == "higa" else algo.upper()
            if algo == "dijkstra": algo_name = "Dijkstra"
            df['Algo'] = algo_name
            dfs.append(df)
        else:
            print(f"⚠️ 警告: 缺失文件 {csv_path}")
    
    if not dfs:
        return None
    return pd.concat(dfs, ignore_index=True)

def save_plot(fig, filename):
    """保存图片到对应的 session 子目录"""
    output_path = os.path.join(BASE_OUTPUT_DIR, CURRENT_SESSION_ID)
    if not os.path.exists(output_path):
        os.makedirs(output_path)
    path = os.path.join(output_path, filename)
    fig.savefig(path, dpi=300, bbox_inches='tight')
    print(f"   💾 已保存: {path}")
    plt.close(fig)

def plot_delay(df):
    """画时延对比图"""
    print("📊 正在绘制: 端到端时延对比...")
    # 只看成功的请求
    df_success = df[df['Success'] == True]
    
    plt.figure(figsize=(10, 6))
    ax = sns.barplot(data=df_success, x="Type", y="Delay", hue="Algo", 
                     palette="viridis", errorbar=None) # 不显示误差棒让图更干净
    
    ax.set_title(f"Average End-to-End Delay (N={GLOBAL_REQ_COUNT})", fontsize=14)
    ax.set_ylabel("Delay (ms)", fontsize=12)
    ax.set_xlabel("Service Type", fontsize=12)
    ax.legend(title="Algorithm")
    
    # 给柱子标数值
    for container in ax.containers:
        ax.bar_label(container, fmt='%.0f', padding=3, fontsize=10)
        
    save_plot(plt.gcf(), "comparison_delay.png")

def plot_loss(df):
    """画丢包率对比图"""
    print("📊 正在绘制: 丢包率对比...")
    df_success = df[df['Success'] == True]
    
    plt.figure(figsize=(10, 6))
    # 将 Loss 转换为百分比
    df_plot = df_success.copy()
    df_plot['Loss_Pct'] = df_plot['Loss'] * 100
    
    ax = sns.barplot(data=df_plot, x="Type", y="Loss_Pct", hue="Algo", 
                     palette="magma", errorbar=None)
    
    ax.set_title(f"Average Packet Loss Rate (N={GLOBAL_REQ_COUNT})", fontsize=14)
    ax.set_ylabel("Packet Loss (%)", fontsize=12)
    ax.set_xlabel("Service Type", fontsize=12)
    
    # 标注数值
    for container in ax.containers:
        ax.bar_label(container, fmt='%.1f%%', padding=3, fontsize=9)
        
    save_plot(plt.gcf(), "comparison_loss.png")

def plot_time_cost(df):
    """画计算耗时对比图 (对数坐标)"""
    print("📊 正在绘制: 算法耗时对比...")
    
    plt.figure(figsize=(8, 6))
    ax = sns.barplot(data=df, x="Algo", y="TimeCost", 
                     palette="Blues_d", errorbar=None)
    
    ax.set_title(f"Average Computational Time Cost (N={GLOBAL_REQ_COUNT})", fontsize=14)
    ax.set_ylabel("Time Cost (ms)", fontsize=12)
    ax.set_xlabel("Algorithm", fontsize=12)
    
    # 使用对数坐标，因为 H-IGA 比 Dijkstra 慢很多
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(ticker.ScalarFormatter()) # 显示真实数值而不是 10^x
    
    for container in ax.containers:
        ax.bar_label(container, fmt='%.1f', padding=3)
        
    save_plot(plt.gcf(), "comparison_timecost.png")

def plot_hops(df):
    """画跳数对比图"""
    print("📊 正在绘制: 路径跳数对比...")
    df_success = df[df['Success'] == True]
    
    plt.figure(figsize=(10, 6))
    ax = sns.barplot(data=df_success, x="Type", y="Hops", hue="Algo", 
                     palette="Set2", errorbar=None)
    
    ax.set_title(f"Average Path Hops (N={GLOBAL_REQ_COUNT})", fontsize=14)
    ax.set_ylabel("Hop Count", fontsize=12)
    ax.set_xlabel("Service Type", fontsize=12)
    
    # 调整Y轴刻度为整数
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    
    for container in ax.containers:
        ax.bar_label(container, fmt='%.1f', padding=3)
        
    save_plot(plt.gcf(), "comparison_hops.png")

def main():
    global CURRENT_SESSION_ID
    # 1. 自动寻找数据
    session_dir = get_latest_session_dir()
    if not session_dir: return
    
    # 获取 Session ID 用于输出目录名
    CURRENT_SESSION_ID = os.path.basename(session_dir)
    
    # 2. 加载数据
    df = load_data(session_dir)
    if df is None:
        print("❌ 数据加载失败，请检查 CSV 文件")
        return

    # 3. 绘图
    print(f"✅ 数据加载成功 (Total: {len(df)} records). 开始绘图...")
    
    plot_delay(df)
    plot_loss(df)
    plot_time_cost(df)
    plot_hops(df)
    
    print(f"\n✨ 所有图表已保存至: {os.path.join(BASE_OUTPUT_DIR, CURRENT_SESSION_ID)}")

if __name__ == "__main__":
    main()