# -*- coding: utf-8 -*-
"""
File: src/data_loader.py
Description: STK 数据加载器 (修复 CSV 列匹配 Bug)
"""
import os
import pandas as pd
import numpy as np
import re
import csv
from datetime import datetime

class STKDataLoader:
    def __init__(self):
        self.epoch = None 

    def load_stk_report(self, file_path, report_type='Access'):
        if report_type == 'Access':
            return self._parse_chain_access_report(file_path)
        elif report_type == 'AER':
            return self._parse_aer_report(file_path)
        else:
            return {}

    def load_ephemeris(self, file_path):
        """加载星历"""
        try:
            # 1. 尝试作为标准 CSV 星历解析
            df = self._parse_csv_ephemeris(file_path)
            if df is not None and not df.empty: return df
            
            # 2. 如果失败，尝试旧的文本解析逻辑
            df = self._parse_dynamic_ephemeris_text(file_path)
            if df is not None and not df.empty: return df

            # 3. 静态解析 (保底)
            return self._parse_static_facility(file_path)
        except:
            return self._parse_static_facility(file_path)

    # =========================================================================
    # CSV 星历解析 (修复列索引覆盖问题)
    # =========================================================================
    def _parse_csv_ephemeris(self, file_path):
        """
        专门解析带表头的 CSV 星历文件
        """
        data = []
        
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            header_line = f.readline().strip()
            # 检查是否有典型的 CSV 表头特征
            if not ('"Time' in header_line and 'Lat' in header_line and ',' in header_line):
                return None
            
            f.seek(0)
            reader = csv.reader(f)
            
            try:
                headers = next(reader) # 读取第一行
            except StopIteration:
                return None
            
            # 建立列名到索引的映射
            col_map = {h.strip().strip('"'): i for i, h in enumerate(headers)}
            
            idx_time, idx_lat, idx_lon, idx_alt = -1, -1, -1, -1
            
            for h, i in col_map.items():
                # [关键修复] 必须排除 'Rate'，否则会读到速度列
                if 'Time' in h: idx_time = i
                if 'Lat' in h and 'Rate' not in h: idx_lat = i
                if 'Lon' in h and 'Rate' not in h: idx_lon = i
                if 'Alt' in h and 'Rate' not in h: idx_alt = i
            
            if idx_time == -1 or idx_lat == -1 or idx_lon == -1:
                return None 

            for row in reader:
                if not row or len(row) < 4: continue
                
                try:
                    t_str = row[idx_time]
                    t_val = self._parse_utc(t_str)
                    
                    if t_val is not None:
                        lat = float(row[idx_lat])
                        lon = float(row[idx_lon])
                        alt = float(row[idx_alt]) if idx_alt != -1 else 0.0
                        data.append([t_val, lat, lon, alt])
                except (ValueError, IndexError):
                    continue

        if data:
            return pd.DataFrame(data, columns=['SimTime', 'Lat', 'Lon', 'Alt'])
        return None

    # =========================================================================
    # 旧版解析逻辑
    # =========================================================================
    def _parse_dynamic_ephemeris_text(self, file_path):
        """解析非标准 CSV 的文本星历"""
        data = []
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        time_pat = r"(\d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2}(?:\.\d+)?)"
        start_reading = False
        
        for line in lines:
            if "Time" in line and "Lat" in line:
                start_reading = True
                continue
            if not start_reading: continue
            if not line.strip() or not line[0].isdigit(): continue
            
            time_match = re.search(time_pat, line)
            if time_match:
                t_val = self._parse_utc(time_match.group(1))
                if t_val is not None:
                    nums = re.findall(r"[-+]?\d*\.\d+", line)
                    if len(nums) >= 3:
                        data.append([t_val, float(nums[-3]), float(nums[-2]), float(nums[-1])])

        if data:
            return pd.DataFrame(data, columns=['SimTime', 'Lat', 'Lon', 'Alt'])
        return None

    # =========================================================================
    # 通用工具
    # =========================================================================
    def _parse_utc(self, time_str):
        try:
            dt = datetime.strptime(time_str, "%d %b %Y %H:%M:%S.%f")
        except ValueError:
            try: 
                dt = datetime.strptime(time_str, "%d %b %Y %H:%M:%S")
            except:
                return None

        if self.epoch is None:
            self.epoch = dt
        delta = dt - self.epoch
        return delta.total_seconds()

    def _parse_static_facility(self, file_path):
        with open(file_path, 'r', errors='ignore') as f: c = f.read()
        nums = [float(x) for x in re.findall(r'-?\d+\.\d+|-?\d+', c)]
        lat, lon, alt = 0.0, 0.0, 0.0
        if len(nums) >= 3:
            lat, lon, alt = nums[-3], nums[-2], nums[-1]
        elif len(nums) >= 2:
            lat, lon = nums[0], nums[1]
        times = np.arange(0, 86401, 60)
        return pd.DataFrame({'SimTime': times, 'Lat': lat, 'Lon': lon, 'Alt': alt})
    
    def _parse_chain_access_report(self, file_path):
        data_map = {} 
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        time_pat = r"(\d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2}(?:\.\d+)?)"
        
        for line in lines:
            line = line.strip()
            if not line or not line[0].isdigit(): continue
            if "To " not in line or "From " not in line: continue
            
            parts = line.split("   ") 
            parts = [p.strip() for p in parts if p.strip()]
            to_node = None
            from_node = None
            for p in parts:
                if p.startswith("To "): to_node = p[3:].strip().split(" ")[-1]
                if p.startswith("From "): from_node = p[5:].strip().split(" ")[-1]
            
            if not to_node or not from_node: continue
            u, v = self._clean_name(from_node), self._clean_name(to_node)
            times = re.findall(time_pat, line)
            if len(times) < 2: continue
            
            t_start = self._parse_utc(times[0])
            t_stop = self._parse_utc(times[1])
            
            if t_start is not None and t_stop is not None:
                pair = (u, v)
                if pair not in data_map: data_map[pair] = []
                data_map[pair].append([t_start, t_stop])
                
        result = {}
        for pair, rows in data_map.items():
            result[pair] = pd.DataFrame(rows, columns=['StartTime', 'StopTime'])
        return result

    def _parse_aer_report(self, file_path):
        data_map = {}
        current_pair = None
        current_data = []
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: lines = f.readlines()
        time_pat = r"(\d{1,2} [A-Z][a-z]{2} \d{4} \d{2}:\d{2}:\d{2}(?:\.\d+)?)"

        for line in lines:
            line = line.strip()
            if not line: continue
            if " to " in line and not line[0].isdigit():
                parts = line.split(" to ")
                if len(parts) == 2:
                    u = parts[0].strip().split(" ")[-1]
                    v = parts[1].strip().split(" ")[-1]
                    if current_pair and current_data:
                        data_map[current_pair] = pd.DataFrame(current_data, columns=['SimTime', 'Range'])
                    current_pair = (self._clean_name(u), self._clean_name(v))
                    current_data = []
                continue
            if not line[0].isdigit(): continue
            time_match = re.search(time_pat, line)
            if time_match:
                t_val = self._parse_utc(time_match.group(1))
                if t_val is not None:
                    nums = re.findall(r"[-+]?\d*\.\d+|\d+", line)
                    if len(nums) > 0:
                        rng = float(nums[-1]) 
                        current_data.append([t_val, rng])
        if current_pair and current_data:
            data_map[current_pair] = pd.DataFrame(current_data, columns=['SimTime', 'Range'])
        return data_map

    def _clean_name(self, name):
        return name.replace('-To-', '').strip()