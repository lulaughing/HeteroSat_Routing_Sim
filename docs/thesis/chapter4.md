# 第四章 仿真实验与结果分析

本章将详细介绍异构卫星网络路由算法的仿真实验环境、参数设置及对比分析结果。实验旨在验证所提 H-IGA 算法在多层异构、高动态及非均匀业务负载场景下的性能优势，特别是针对跨层链路拥塞的缓解能力。

## 4.1 仿真场景与参数设置

### 4.1.1 仿真平台与拓扑构建
仿真实验基于 Python 平台开发，采用 STK (Systems Tool Kit) 软件生成高精度的卫星轨道星历与链路可见性数据。仿真场景构建了一个包含探测层 (Detect)、低轨通信层 (LEO)、中轨骨干层 (MEO)、高轨覆盖层 (GEO) 以及地面站 (Ground) 的四层异构天地一体化网络拓扑。

网络节点配置如下：
- **探测层 (Detect)**: 100 颗低轨探测卫星，负责生成遥感数据，轨道高度较低，主要作为业务源节点。
- **通信层 (LEO)**: 225 颗低轨通信卫星，作为接入层与中继层，负责汇聚底层数据并向上传输。
- **骨干层 (MEO)**: 8 颗中轨卫星，构成核心骨干网，提供大容量、长距离的数据中继。
- **覆盖层 (GEO)**: 3 颗地球同步轨道卫星，提供全球覆盖与应急备份。
- **地面站 (Facility)**: 48 个全球分布的地面信关站，作为业务的最终落地接收端。

全网共计 384 个节点。仿真利用 STK 导出的真实星历数据，以 10秒 为时间步长，动态计算节点位置与链路可见性。为了模拟真实的异构网络特性，不同层级间的链路带宽与通信距离限制采用了非均匀配置，如表 4-1 所示。

\begin{table}[htbp]
\caption{异构网络链路参数配置}
\centering
\begin{tabular}{lccc}
\toprule
\textbf{链路类型} & \textbf{带宽 (Mbps)} & \textbf{传播时延 (ms)} & \textbf{基础丢包率 (\%)} \\
\midrule
Ground $\leftrightarrow$ LEO/Detect & 100 & 2.4 $\sim$ 13.2 & 0.1 \\
Ground $\leftrightarrow$ MEO/GEO & 100 & 50.0 $\sim$ 130.0 & 0.1 \\
MEO $\leftrightarrow$ MEO/GEO & 100 & 60.0 $\sim$ 150.0 & 0.1 \\
LEO/Detect $\leftrightarrow$ MEO & 60 & 20.0 $\sim$ 45.5 & 0.1 \\
LEO/Detect $\leftrightarrow$ GEO & 60 & 117.0 $\sim$ 135.0 & 0.1 \\
Detect $\leftrightarrow$ LEO & 30 & 1.0 $\sim$ 24.0 & 0.1 \\
LEO/Detect $\leftrightarrow$ LEO/Detect & 30 & 1.4 $\sim$ 15.0 & 0.1 \\
\bottomrule
\end{tabular}
\label{tab:link_params}
\end{table}

其中，“跨层接入”链路（LEO/Detect $\to$ MEO）被特意设计为网络的**关键瓶颈**。其 60 Mbps 的带宽在承载多条宽带遥感业务（35 Mbps/条）时，一旦发生并发（如 2 条流共需 70 Mbps），极易产生拥塞。

### 4.1.2 链路物理模型
为了真实反映网络负载对传输质量的影响，仿真采用了基于 M/M/1 排队论的非线性链路代价模型。

**1. 动态时延模型**
链路的总时延 $D_{total}$ 由传播时延 $D_{prop}$ 和排队时延 $D_{queue}$ 组成。其中传播时延取决于实时链路距离 $d$：
$$ D_{prop} = d / c $$
排队时延与链路利用率 $u$ ($u = \text{UsedBW} / \text{Capacity}$) 呈非线性关系。当 $u \ge 1.0$ 时，排队时延呈指数级爆炸增长，以模拟严重的缓冲区积压：
$$
D_{queue}(u) = 
\begin{cases} 
1.0 & u < 0.9 \\
\frac{1}{1-u} & 0.9 \le u < 1.0 \\
10 + (u-1) \times 200 & u \ge 1.0 \text{ (拥塞惩罚)}
\end{cases}
$$

**2. 动态丢包模型**
丢包率 $L$ 同样基于负载率动态计算，模拟拥塞导致的队列溢出：
$$
L(u) = 
\begin{cases} 
0.1\% & u \le 0.9 \\
0.1\% + (u-0.9) \times 0.5 & 0.9 < u \le 1.0 \\
1 - \frac{1}{1.5u} & u > 1.0 \text{ (严重丢包)}
\end{cases}
$$
该模型确保了当流量超过链路容量时，丢包率会迅速上升（例如 $u=2.0$ 时丢包率约为 66\%），从而迫使路由算法必须具备拥塞规避能力。

### 4.1.3 业务流量模型
实验构建了“热点区域”与“背景流量”混合的非均匀业务场景，以测试算法在局部高负载下的性能。

1.  **业务分布**：
    -   **热点走廊 (90\%)**: 源节点集中在北美西海岸 (Lat: $30^{\circ}\sim40^{\circ}$, Lon: $-125^{\circ}\sim-115^{\circ}$)，宿节点集中在东亚区域 (Lat: $30^{\circ}\sim40^{\circ}$, Lon: $130^{\circ}\sim145^{\circ}$)。这种跨洋长距离传输强迫流量汇聚于有限的 MEO/GEO 骨干节点，制造激烈的跨层资源竞争。
    -   **背景噪声 (10\%)**: 全球范围内随机选取的源宿节点对，用于模拟背景通信负载。

2.  **多级 QoS 业务类型**：
    实验定义了三种不同 QoS 需求的业务流，如表 4-2 所示。其中“遥感数据”是重点考察对象，其高带宽需求（45 Mbps）极易触发跨层链路（60 Mbps）的拥塞。

\begin{table}[htbp]
\caption{多级 QoS 业务类型定义}
\centering
\begin{tabular}{lcccc}
\toprule
\textbf{业务类型} & \textbf{带宽 (Mbps)} & \textbf{时延容限 (ms)} & \textbf{丢包率容限} & \textbf{优先级} \\
\midrule
Voice Critical (语音) & 1 & 180 & $10^{-3}$ & High (0.8) \\
Remote Sensing (遥感) & \textbf{45} & 2000 & $10^{-2}$ & Medium (0.3) \\
Best Effort (尽力而为) & 5 & 800 & $5 \times 10^{-2}$ & Low (0.5) \\
\bottomrule
\end{tabular}
\label{tab:service_types}
\end{table}

### 4.1.4 算法参数设置
为了验证本文提出的分层拥塞感知算法 (H-IGA) 的性能，实验将其与传统的 Dijkstra 最短路径算法（以时延为权重）进行对比。H-IGA 的核心进化参数设置如表 4-3 所示。

\begin{table}[htbp]
\caption{H-IGA 算法参数设置}
\centering
\begin{tabular}{lc}
\toprule
\textbf{参数名称} & \textbf{数值} \\
\midrule
种群规模 (Population Size) & 30 \\
最大迭代次数 (Max Iterations) & 20 \\
交叉概率 ($P_c$) & 0.8 \\
变异概率 ($P_m$) & 0.1 \\
适应度权重 ($\alpha$: 时延, $\beta$: 丢包) & $\alpha=0.6, \beta=0.4$ \\
拥塞规避阈值 ($\rho_{th}$) & 0.7 \\
\bottomrule
\end{tabular}
\label{tab:iga_params}
\end{table}
