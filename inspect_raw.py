# -*- coding: utf-8 -*-
import os

def peek_file(path, num_lines=30):
    print(f"\nScanning: {os.path.basename(path)}")
    print("-" * 50)
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for _ in range(num_lines):
                print(f.readline().strip())
    except Exception as e:
        print(f"Error reading file: {e}")
    print("-" * 50)

# 只需要看一个 Detect 的星历文件
ephemeris_dir = r"F:\HeteroSat_Routing_Sim\data\raw_stk\Ephemeris_Data\Detect"
files = [f for f in os.listdir(ephemeris_dir) if f.endswith('.txt')]
if files:
    peek_file(os.path.join(ephemeris_dir, files[0]))
else:
    print("找不到 Detect 星历文件")