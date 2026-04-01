# -*- coding: utf-8 -*-
"""
File: config/settings.py
Description: 全局配置参数 (路径、物理常数、算法参数)
"""
import os

# 1. 路径配置
# =========================================================
# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 数据目录
DATA_ROOT = os.path.join(BASE_DIR, 'data')
RAW_DATA_DIR = os.path.join(DATA_ROOT, 'raw_stk')
PROCESSED_DATA_DIR = os.path.join(DATA_ROOT, 'processed')

# [关键修复] topology.py 依赖这个字典
DATA_DIRS = {
    'ephemeris': os.path.join(RAW_DATA_DIR, 'Ephemeris_Data'),
    'access':    os.path.join(RAW_DATA_DIR, 'links_access_Data'),
    'aer':       os.path.join(RAW_DATA_DIR, 'links_access_AER')
}

# Backward-compatible aliases used by older tests/scripts.
EPHEMERIS_DIR = DATA_DIRS['ephemeris']
ACCESS_DATA_DIR = DATA_DIRS['access']
ACCESS_AER_DIR = DATA_DIRS['aer']

# 缓存目录
CACHE_DIR = PROCESSED_DATA_DIR

# 结果输出目录
RESULTS_DIR = os.path.join(DATA_ROOT, 'results')

# 确保目录存在
os.makedirs(PROCESSED_DATA_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# 2. 仿真常数
# =========================================================
SIM_DURATION = 100   # 默认仿真时长 (s)
TIME_STEP = 10       # 时间步长 (s)

# 3. 算法参数 (IGA)
# =========================================================
IGA_PARAMS = {
    'pop_size': 30,      # 种群大小
    'max_iter': 20,      # 最大迭代次数
    'pc': 0.8,           # 交叉概率
    'pm': 0.1,           # 变异概率
    'alpha': 0.6,        # 适应度权重: 时延
    'beta': 0.4,         # 适应度权重: 丢包
    'rho_th': 0.7        # 拥塞阈值
}

# 4. 链路参数默认值
# =========================================================
DEFAULT_LINK_BW = 1000.0  # Mbps
DEFAULT_LINK_DELAY = 10.0 # ms
DEFAULT_LINK_LOSS = 0.001 # 0.1%

# =========================================================
# [修正] 表1 节点间传输距离限制 (放宽版)
# 策略：宽进严选。让 Top-4 算法去挑最近的，这里只做保底。
# =========================================================
LINK_RANGE_LIMITS = {
    ('Detect', 'Detect'): 10000, # 足够覆盖同轨和异轨
    ('LEO', 'LEO'):       8000,  # 足够覆盖同轨和异轨
    
    ('LEO', 'MEO'):       12000,
    ('MEO', 'GEO'):       50000,
    ('LEO', 'GEO'):       50000,
    
    ('Detect', 'LEO'):    5000,  # 层间链路
    ('Detect', 'MEO'):    12000,
    ('Detect', 'GEO'):    50000,
    
    ('Ground', 'Detect'): 6000,
    ('Ground', 'LEO'):    6000,
    ('Ground', 'MEO'):    15000,
    ('Ground', 'GEO'):    60000
}
