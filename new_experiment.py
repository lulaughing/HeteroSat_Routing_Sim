# new_experiment.py
import os

ANCHOR_FILE = os.path.join("logs", "current_session.txt")

def main():
    if os.path.exists(ANCHOR_FILE):
        try:
            os.remove(ANCHOR_FILE)
            print("✅ 上一次实验会话已结束。")
            print("🚀 下一个运行的脚本将自动创建全新的 Session 目录。")
        except Exception as e:
            print(f"❌ 无法删除锚点文件: {e}")
    else:
        print("ℹ️ 当前没有活跃的会话，无需重置。")

if __name__ == "__main__":
    main()