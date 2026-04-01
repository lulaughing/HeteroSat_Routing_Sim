import matplotlib.pyplot as plt
import numpy as np

# 设置绘图风格
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Arial', 'DejaVu Sans']

def draw_network_mapping():
    fig = plt.figure(figsize=(10, 8), dpi=150)
    ax = fig.add_subplot(111, projection='3d')

    # === 参数设置 ===
    grid_size = 3
    z_phys = 10  # 物理层高度
    z_logic = 0  # 逻辑层高度
    offset = 0.5 # 边距

    # 生成网格坐标 (0,0) 到 (2,2)
    x, y = np.meshgrid(np.arange(grid_size), np.arange(grid_size))
    x = x.flatten()
    y = y.flatten()
    
    # === 1. 绘制层平面基底 (Visual Planes) ===
    # 物理层平面 (浅红/灰背景)
    xx, yy = np.meshgrid([-0.5, 2.5], [-0.5, 2.5])
    ax.plot_surface(xx, yy, np.full_like(xx, z_phys), color='lightblue', alpha=0.1, shade=False)
    # 逻辑层平面 (白色/网格背景)
    ax.plot_surface(xx, yy, np.full_like(xx, z_logic), color='whitesmoke', alpha=0.1, shade=False)

    # === 2. 绘制网格连线 (Topology Lines) ===
    # 绘制物理层实线 (黑色)
    for i in range(grid_size):
        ax.plot([i, i], [0, grid_size-1], [z_phys, z_phys], color='black', linewidth=1, alpha=0.3, zorder=1) # 垂直线
        ax.plot([0, grid_size-1], [i, i], [z_phys, z_phys], color='black', linewidth=1, alpha=0.3, zorder=1) # 水平线
    
    # 绘制逻辑层虚线 (灰色)
    for i in range(grid_size):
        ax.plot([i, i], [0, grid_size-1], [z_logic, z_logic], color='gray', linestyle=':', linewidth=0.8, alpha=0.5)
        ax.plot([0, grid_size-1], [i, i], [z_logic, z_logic], color='gray', linestyle=':', linewidth=0.8, alpha=0.5)

    # === 3. 绘制投影线 (Projection Lines) ===
    for i in range(len(x)):
        ax.plot([x[i], x[i]], [y[i], y[i]], [z_logic, z_phys], 
                color='gray', linestyle='--', linewidth=0.8, alpha=0.4)

    # === 4. 定义并绘制路径 (The Path) ===
    # 假设路径: (0,0) -> (0,1) -> (1,1) -> (2,1) -> (2,2)
    path_x = [0, 0, 1, 2, 2]
    path_y = [0, 1, 1, 1, 2]
    
    # 物理层路径 (粗蓝色实线)
    ax.plot(path_x, path_y, [z_phys]*len(path_x), color='#1f77b4', linewidth=3, label='Physical Path', zorder=10)
    
    # 逻辑层路径 (蓝色虚线)
    ax.plot(path_x, path_y, [z_logic]*len(path_x), color='#1f77b4', linestyle='--', linewidth=2, label='Logical Path', zorder=5)

    # === 5. 绘制节点 (Nodes) ===
    # 物理层节点 (卫星 - 使用大方块或圆代表)
    # 为了模拟卫星，我们用大的 Marker
    ax.scatter(x, y, [z_phys]*len(x), c='white', edgecolors='black', s=300, marker='s', alpha=1, depthshade=False, zorder=20)
    # 给卫星加文字标签 S_ij
    for i in range(len(x)):
        label = f"$S_{{{x[i]},{y[i]}}}$"
        ax.text(x[i], y[i], z_phys + 0.5, label, ha='center', va='bottom', fontsize=9, zorder=25)

    # 逻辑层节点 (实心圆点)
    ax.scatter(x, y, [z_logic]*len(x), c='black', s=50, marker='o', depthshade=False, zorder=20)
    # 给逻辑节点加坐标标签
    for i in range(len(x)):
        label = f"$({x[i]},{y[i]})$"
        ax.text(x[i], y[i], z_logic - 0.8, label, ha='center', va='top', fontsize=8, color='gray')

    # === 6. 美化设置 ===
    # 隐藏坐标轴刻度，只保留立体感
    ax.set_axis_off()
    
    # 设置视角 (Elev=高度角, Azim=方位角)
    ax.view_init(elev=25, azim=-60)
    
    # 添加层级标注
    ax.text(-1, 3, z_phys, "Physical Topology\n(Satellites)", fontsize=12, fontweight='bold', color='#333')
    ax.text(-1, 3, z_logic, "Logical Grid\n(Virtual Nodes)", fontsize=12, fontweight='bold', color='#333')
    
    # 添加映射标注
    ax.text(3, 1.5, 5, "Mapping Projection", fontsize=10, color='gray', rotation=90)

    # 调整布局
    plt.tight_layout()
    
    # 保存或显示
    # plt.savefig('figure_4_4_topology_mapping.pdf', bbox_inches='tight') # 建议保存为PDF
    plt.show()

if __name__ == "__main__":
    draw_network_mapping()