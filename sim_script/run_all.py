# -*- coding: utf-8 -*-
"""
File: sim_script/run_all.py
Description: 一键运行所有仿真对比 (Dijkstra, SGA, H-IGA)
确保所有算法在同一套流量请求下运行，并输出到同一个 Session 目录。
"""
import subprocess
import sys
import os
import time

# 将项目根目录添加到路径
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

# [关键] 设置仿真时间窗口
# 如果只想跑特定时间点（如 300s）的拓扑，可以设置 START=300, DURATION=1, STEP=1
if 'HETEROSAT_SIM_START' not in os.environ:
    os.environ['HETEROSAT_SIM_START'] = '300'
if 'HETEROSAT_SIM_DURATION' not in os.environ:
    os.environ['HETEROSAT_SIM_DURATION'] = '1'
if 'HETEROSAT_TIME_STEP' not in os.environ:
    os.environ['HETEROSAT_TIME_STEP'] = '1'
if 'HETEROSAT_REQUESTS_PER_STEP' not in os.environ:
    os.environ['HETEROSAT_REQUESTS_PER_STEP'] = '300' #业务条数

from src.utils import ANCHOR_FILE, get_session_dir

def run_script(script_name, session_dir):
    """运行单个仿真脚本"""
    script_path = os.path.join(ROOT_DIR, "sim_script", script_name)
    print(f"\n" + "="*60)
    print(f"[Master] Starting: {script_name}")
    print(f"Session: {session_dir}")
    print("="*60)
    
    # 继承当前环境变量，确保 PYTHONPATH 正确
    env = os.environ.copy()
    env["PYTHONPATH"] = ROOT_DIR
    
    # 运行子进程
    process = subprocess.Popen(
        [sys.executable, script_path],
        env=env,
        text=True
    )
    process.wait()
    
    if process.returncode == 0:
        print(f"[Master] Finished: {script_name}")
    else:
        print(f"[Master] Error in {script_name} (Exit Code: {process.returncode})")
    
    return process.returncode

def main():
    t_start = time.time()
    session_dir = get_session_dir()
    
    scripts = [
        "run_dijkstra.py", # 扁平化基线
        "run_dijkstra_qos.py", # 基线QoS-Dijkstra
        "run_sga.py",      # 分层基线 (标准遗传算法)
        "run_higa.py"      # 本文方法 (分层 + 改进遗传算法)
    ]
    
    # 确保 session 目录已通过 src.utils 创建并锁定
    print(f"[Master] Simulation Suite Started.")
    print(f"Results will be saved in: {session_dir}")
    
    try:
        # 顺序执行各算法脚本
        for script in scripts:
            ret = run_script(script, session_dir)
            if ret != 0:
                print(f"[Master] Stopping execution due to error in {script}")
                # 注意：这里 break 后会直接进入 finally 块清理文件
                break
                
        duration = time.time() - t_start
        print(f"\n" + "="*60)
        print(f"[Master] All Simulations Completed in {duration:.1f}s.")
        print(f"Session Directory: {session_dir}")
        print("="*60)

    finally:
        # [关键修改] 使用 finally 块确保无论何种情况退出（正常/报错/中断），都会执行清理
        if os.path.exists(ANCHOR_FILE):
            try:
                os.remove(ANCHOR_FILE)
                print(f"\n[Master] Anchor file cleared. Next run will create a new session.")
            except Exception as e:
                print(f"[Master] Failed to clear anchor file: {e}")

if __name__ == "__main__":
    main()
