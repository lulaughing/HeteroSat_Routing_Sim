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

# [关键] 在导入 SESSION_DIR 之前，可以根据需要手动设置环境变量
# 这样 SESSION_DIR 的初始化就会读取到这个值
if 'HETEROSAT_REQUESTS_PER_STEP' not in os.environ:
    os.environ['HETEROSAT_REQUESTS_PER_STEP'] = '100' # 默认值

from src.utils import SESSION_DIR, ANCHOR_FILE

def run_script(script_name):
    """运行单个仿真脚本"""
    script_path = os.path.join(ROOT_DIR, "sim_script", script_name)
    print(f"\n" + "="*60)
    print(f"🚀 [Master] Starting: {script_name}")
    print(f"📅 Session: {SESSION_DIR}")
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
        print(f"✅ [Master] Finished: {script_name}")
    else:
        print(f"❌ [Master] Error in {script_name} (Exit Code: {process.returncode})")
    
    return process.returncode

def main():
    t_start = time.time()
    
    scripts = [
        "run_dijkstra.py", # 扁平化基线
        "run_dijkstra_qos.py", # 基线QoS-Dijkstra
        "run_sga.py",      # 分层基线 (标准遗传算法)
        "run_higa.py"      # 本文方法 (分层 + 改进遗传算法)
    ]
    
    # 确保 session 目录已通过 src.utils 创建并锁定
    print(f"🌟 [Master] Simulation Suite Started.")
    print(f"📂 Results will be saved in: {SESSION_DIR}")
    
    for script in scripts:
        ret = run_script(script)
        if ret != 0:
            print(f"⚠️ [Master] Stopping execution due to error in {script}")
            break
            
    # 运行结束，清理锚点文件，以便下次运行生成新 session
    if os.path.exists(ANCHOR_FILE):
        try:
            os.remove(ANCHOR_FILE)
            print(f"\n🧹 [Master] Anchor file cleared. Next run will create a new session.")
        except Exception as e:
            print(f"⚠️ [Master] Failed to clear anchor file: {e}")

    duration = time.time() - t_start
    print(f"\n" + "="*60)
    print(f"🏁 [Master] All Simulations Completed in {duration:.1f}s.")
    print(f"📁 Session Directory: {SESSION_DIR}")
    print("="*60)

if __name__ == "__main__":
    main()
