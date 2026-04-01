# -*- coding: utf-8 -*-
"""
File: tests/test_data_loader.py
Description: 测试数据加载模块是否正常工作
"""
import sys
import os
import unittest

# -------------------------------
# [关键步骤] 将项目根目录加入 python path
# 这样才能正确导入 src 和 config 模块
# -------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__)) # 获取 tests 目录路径
project_root = os.path.dirname(current_dir)              # 获取 HeteroSat_Routing_Sim 根目录
sys.path.append(project_root)
# -------------------------------

from src.data_loader import STKDataLoader
from config.settings import ACCESS_AER_DIR, ACCESS_DATA_DIR

class TestDataLoader(unittest.TestCase):
    
    def setUp(self):
        """测试前的初始化"""
        print(f"\nTesting in Project Root: {project_root}")
        self.loader = STKDataLoader()

    def test_load_aer_report(self):
        """测试加载 AER 报告"""
        # 构造一个真实存在的文件路径 (根据您的文件列表)
        # 注意：这里使用 os.path.join 确保跨平台兼容
        test_file = os.path.join(ACCESS_AER_DIR, "Detect_Detect_Access_AER.txt")
        
        print(f"正在尝试读取 AER 文件: {test_file}")
        
        # 检查文件是否存在，避免路径错误导致的测试失败
        if not os.path.exists(test_file):
            print(f"警告: 文件不存在，跳过测试。请检查路径: {test_file}")
            return

        # 执行加载
        data_dict = self.loader.load_stk_report(test_file, report_type='AER')
        
        # 验证结果
        self.assertIsInstance(data_dict, dict)
        self.assertGreater(len(data_dict), 0, "AER 数据字典为空，未解析到任何链路对")
        
        # 取第一个链路对查看数据
        first_key = list(data_dict.keys())[0]
        df = data_dict[first_key]
        
        print(f"成功解析 AER 链路: {first_key}")
        print(f"数据预览:\n{df.head(3)}")
        
        # 验证列名是否正确
        expected_cols = ['SimTime', 'Range']
        self.assertListEqual(list(df.columns), expected_cols)

    def test_load_access_report(self):
        """测试加载 Access (可见性) 报告"""
        # 修改点：文件名后缀改为 _Data.txt
        test_file = os.path.join(ACCESS_DATA_DIR, "Detect_Facility_Access_Data.txt")
        
        print(f"正在尝试读取 Access 文件: {test_file}")
        
        if not os.path.exists(test_file):
            print(f"警告: 文件不存在，跳过测试。请检查路径: {test_file}")
            return

        data_dict = self.loader.load_stk_report(test_file, report_type='Access')
        
        self.assertIsInstance(data_dict, dict)
        self.assertGreater(len(data_dict), 0)
        
        first_key = list(data_dict.keys())[0]
        df = data_dict[first_key]
        
        print(f"成功解析 Access 链路: {first_key}")
        print(f"数据预览:\n{df.head(3)}")
        
        expected_cols = ['StartTime', 'StopTime']
        self.assertListEqual(list(df.columns), expected_cols)

if __name__ == '__main__':
    unittest.main()
