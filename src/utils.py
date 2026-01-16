# -*- coding: utf-8 -*-
"""
File: src/utils.py
Description: 高级日志管理工具 (支持多文件分流与会话管理)
"""

import logging
import os
import sys
from datetime import datetime
from src.simulation_utils import get_sim_config

# 基础日志根目录
LOG_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
if not os.path.exists(LOG_ROOT):
    os.makedirs(LOG_ROOT)



# ==========================================
# [增量修改] 会话目录管理 (锚点机制)
# 逻辑：检查 logs/current_session.txt，有则复用，无则新建
# ==========================================
ANCHOR_FILE = os.path.join(LOG_ROOT, "current_session.txt")

def _get_or_create_session_dir():
    # 1. 尝试读取锚点文件 (复用现有目录)
    if os.path.exists(ANCHOR_FILE):
        try:
            with open(ANCHOR_FILE, 'r', encoding='utf-8') as f:
                existing_path = f.read().strip()
            # 二次确认目录确实存在
            if os.path.exists(existing_path):
                print(f"日志目录存在: {existing_path}")
                return existing_path
        except Exception:
            pass # 读取出错就降级到新建

    # 2. 创建新会话目录
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # [新增] 获取业务条数参数，加入目录名
    cfg = get_sim_config()
    sim_start = cfg['SIM_START']
    sim_duration = cfg['SIM_DURATION']
    time_step = cfg['TIME_STEP']
    req_count = cfg['REQUESTS_PER_STEP']
    session_name = f"session_{session_id}_T{sim_start}_N{req_count}"
    
    new_dir = os.path.join(LOG_ROOT, session_name)
    if not os.path.exists(new_dir):
        os.makedirs(new_dir)

    # 3. 更新锚点文件
    try:
        with open(ANCHOR_FILE, 'w', encoding='utf-8') as f:
            f.write(new_dir)
        print(f"✨ [System] New Experiment Session Created: {new_dir}")
    except Exception as e:
        print(f"⚠️ [System] Failed to update anchor file: {e}")

    return new_dir

# 全局变量：Session 路径 (所有导入此模块的脚本共享)
SESSION_DIR = _get_or_create_session_dir()
# ==========================================


def get_logger(name, filename, level=logging.INFO, console=True):
    """
    创建一个独立的 Logger 对象
    :param name: Logger 名称 (内部标识)
    :param filename: 输出的文件名
    :param level: 日志级别
    :param console: 是否同时输出到控制台 (默认 True)
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers = [] # 清除旧 handler 防止重复打印

    formatter = logging.Formatter(
        '%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    # 1. 文件 Handler (UTF-8编码)
    file_path = os.path.join(SESSION_DIR, filename)
    fh = logging.FileHandler(file_path, encoding='utf-8')
    fh.setLevel(level)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # 2. 控制台 Handler (可选，用于实时观察)
    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(level)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger

# --- 预定义的三大日志通道 ---

def get_flow_logger():
    """仿真主流程日志 (宏观视角: 业务生成、域间路径、成功/失败)"""
    return get_logger('FLOW', 'sim_flow.log', level=logging.INFO, console=True)

def get_algo_logger():
    """算法微观日志 (微观视角: 遗传进化、交叉变异、适应度变化)"""
    # 建议 console=False，因为内容极大，只写文件供事后分析
    return get_logger('ALGO', 'algo_iga_details.log', level=logging.DEBUG, console=False)

def get_net_logger():
    """网络状态日志 (状态视角: 链路拥塞快照、带宽扣除记录)"""
    return get_logger('NET', 'net_state.log', level=logging.INFO, console=False)