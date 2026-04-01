# HeteroSat_Routing_Sim

异构卫星网络路由仿真框架，面向学术研究场景，使用 STK 导出的原始数据和 Python 建模，对 LEO / MEO / GEO 异构星座中的路由策略进行对比仿真。

项目当前主线已经覆盖以下完整流程：

`STK 原始数据 -> 物理拓扑构建 -> 虚拟域划分 -> 域间路由 -> 域内路由 -> 链路状态更新 -> 指标统计 -> 结果落盘/绘图`

## 1. 项目目标

这个项目主要用于研究异构卫星网络中的分层路由问题，重点比较以下几类算法在不同负载条件下的行为差异：

- `Dijkstra`
- `QoS-Dijkstra`
- `SGA`
- `H-IGA`

其中 `H-IGA` 是项目中的重点方法：先在虚拟拓扑上做域间规划，再在物理拓扑上做域内拥塞感知寻路。

## 2. 核心逻辑

### 2.1 数据到拓扑

1. `src/data_loader.py`
   负责解析 STK 导出的星历、Access、AER 数据。

2. `src/topology.py`
   使用解析后的数据构造某个时刻的物理图 `G(t)`：
   - 节点包含类型、经纬度、高度等属性
   - 边包含容量、时延、丢包、距离、已用带宽等属性
   - 使用 `data/processed/topology_cache_v5_dedup.pkl` 做缓存，避免重复解析

3. `src/link_model.py`
   在业务通过链路后，根据 `used_bw / capacity` 更新链路动态时延和丢包率。

### 2.2 物理图到虚拟图

1. `src/routing/hierarchical_mapper.py`
   将物理节点映射到虚拟域：
   - MEO / GEO 节点通常直接作为高层骨干节点
   - LEO / Detect 节点按地理网格聚合成虚拟域
   - 地面节点会归属到接入卫星所在的虚拟域

2. 虚拟图中的边是由物理跨域链路聚合得到的，包含：
   - `capacity`
   - `used_bw`
   - `delay`
   - `loss`
   - `link_count`

### 2.3 路由执行

项目采用分层执行：

1. `src/routing/inter_algo.py`
   在虚拟拓扑上执行域间选路。

2. `src/simulation_utils.py::decompose_and_execute_hierarchical`
   将虚拟路径拆解成多个域内子问题：
   - 选择每一段的边界出口和入口
   - 在物理图中屏蔽非法地面中继
   - 调用域内算法完成每一段寻路
   - 成功后回写虚拟边负载

3. 域内算法可以是：
   - `src/routing/dijkstra.py`
   - `src/routing/sga.py`
   - `src/routing/iga/iga.py`

### 2.4 状态更新与结果统计

每条业务成功后：

1. 在物理图上逐跳调用 `TopologyManager.update_link_state`
2. 链路的 `used_bw`、`delay`、`loss` 被更新
3. 后续业务会在新的网络状态上继续路由
4. 最终输出成功率、时延、丢包、Goodput 等指标

## 3. 当前主线入口

推荐优先使用以下入口：

- `python main.py`
  - 小规模平行对比入口
  - 适合快速检查 Dijkstra 与 H-IGA 的差异

- `python sim_script/run_load_analysis.py`
  - 负载扫描主入口
  - 适合跑论文中的多负载对比实验

- `python sim_script/run_all.py`
  - 顺序运行 `Dijkstra / QoS-Dijkstra / SGA / H-IGA`

## 4. 目录结构

```text
HeteroSat_Routing_Sim/
├── config/
│   ├── settings.py               # 全局路径、缓存、仿真参数
│   └── logging_config.py
├── data/
│   ├── raw_stk/                  # STK 原始导出数据
│   │   ├── Ephemeris_Data/
│   │   ├── links_access_Data/
│   │   └── links_access_AER/
│   ├── processed/                # 预处理缓存
│   └── results/                  # 仿真结果输出
├── src/
│   ├── data_loader.py            # STK 数据解析
│   ├── topology.py               # 时变物理拓扑构建与缓存
│   ├── link_model.py             # 链路动态时延/丢包模型
│   ├── traffic.py                # 业务请求生成
│   ├── simulation_utils.py       # 分层执行与仿真公共逻辑
│   ├── utils.py                  # 日志、session、工具函数
│   └── routing/
│       ├── strategy.py           # 路由算法基类
│       ├── dijkstra.py           # 基准最短路
│       ├── dijkstra_qos.py       # QoS 剪枝版 Dijkstra
│       ├── inter_algo.py         # 虚拟域间路由
│       ├── hierarchical_mapper.py# 物理图到虚拟图映射
│       ├── sga.py                # 标准遗传算法
│       └── iga/                  # H-IGA 实现
│           ├── iga.py
│           ├── iga_init.py
│           ├── iga_fitness.py
│           ├── iga_selection.py
│           ├── iga_crossover.py
│           └── iga_mutation.py
├── sim_script/
│   ├── run_dijkstra.py
│   ├── run_dijkstra_qos.py
│   ├── run_sga.py
│   ├── run_higa.py
│   ├── run_all.py
│   ├── run_load_analysis.py
│   └── run_sensitivity.py
├── test/                         # 单元测试与集成测试
├── plot/                         # 绘图脚本和结果图
├── docs/                         # 论文/文档材料
├── main.py                       # 主入口
├── auto_tune.py                  # 参数调优兼容入口
└── requirements.txt
```

## 5. 关键模块说明

### `src/topology.py`

物理拓扑管理器，负责：

- 读取缓存或原始数据
- 计算稳定链路白名单
- 为不同链路类型设置异构容量
- 在给定时刻生成 NetworkX 物理图

### `src/simulation_utils.py`

当前最重要的公共逻辑文件，包含：

- 流量缓存与加载
- 网络快照日志
- 分层路由执行器
- 仿真参数读取

### `src/routing/inter_algo.py`

负责域间路由，使用虚拟边上的：

- `delay`
- `loss`
- `used_bw`
- `capacity`

综合计算代价，支持拥塞惩罚和业务类型感知权重。

### `src/routing/iga/`

H-IGA 的核心实现，包含：

- 初始化
- 适应度计算
- 选择
- 交叉
- 变异

其中 `iga_fitness.py` 和 `iga_mutation.py` 是 H-IGA 与普通遗传算法差异最大的部分。

## 6. 运行方式

### 安装依赖

```bash
pip install -r requirements.txt
```

### 快速运行

```bash
python main.py
```

### 跑单个算法

```bash
python sim_script/run_dijkstra.py
python sim_script/run_dijkstra_qos.py
python sim_script/run_sga.py
python sim_script/run_higa.py
```

### 跑完整负载分析

```bash
python sim_script/run_load_analysis.py
```

### 跑全部算法

```bash
python sim_script/run_all.py
```

## 7. 环境变量

项目支持通过环境变量控制仿真时间窗口和请求数量：

```bash
HETEROSAT_SIM_START
HETEROSAT_SIM_DURATION
HETEROSAT_TIME_STEP
HETEROSAT_REQUESTS_PER_STEP
```

例如：

```bash
set HETEROSAT_SIM_START=300
set HETEROSAT_SIM_DURATION=1
set HETEROSAT_TIME_STEP=1
set HETEROSAT_REQUESTS_PER_STEP=100
python main.py
```

## 8. 测试

运行全部测试：

```bash
python -m unittest discover -s test -p "test_*.py"
```

运行单个测试文件：

```bash
python -m unittest test.test_routing_mechanisms
python -m unittest test.test_topology_update
```

## 9. 输出结果

运行脚本后，结果通常会写入：

- `logs/session_*/`
  - 路由路径日志
  - 网络状态日志
  - 单次仿真 CSV

- `data/results/`
  - 汇总结果

- `plot/`
  - 绘图脚本和图像输出

## 10. 当前状态说明

当前仓库已经完成一轮主线收敛，建议按下面的理解使用：

- `main.py` 和 `sim_script/` 中的主入口可直接运行
- `src/simulation_utils.py` 是当前公共执行主线
- `src/routing/` 是算法实现主线
- `test/` 当前主线测试已可通过
- 仍有部分历史绘图脚本和诊断脚本保留旧风格输出，但不影响主线仿真

## 11. 适合从哪里开始看代码

如果第一次接触这个项目，建议按下面顺序阅读：

1. `main.py`
2. `src/simulation_utils.py`
3. `src/topology.py`
4. `src/routing/hierarchical_mapper.py`
5. `src/routing/inter_algo.py`
6. `src/routing/iga/iga.py`
7. `src/routing/iga/iga_fitness.py`

这样最容易看清楚整个项目的执行链路。
