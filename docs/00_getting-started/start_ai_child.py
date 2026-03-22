#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Child 启动管理工具

使用方式：
  python start_ai_child.py              # 完整启动流程
  python start_ai_child.py --server     # 仅启动服务器
  python start_ai_child.py --check      # 检查环境
  python start_ai_child.py --reset      # 重置数据库
"""

import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent
SERVER_DIR = PROJECT_ROOT / "server"
VENV_DIR = SERVER_DIR / ".venv"
ENV_FILE = SERVER_DIR / ".env"
DB_FILE = SERVER_DIR / "ai_child.db"

class Startup:
    """AI Child 启动管理器"""
    
    def __init__(self):
        self.project_root = PROJECT_ROOT
        self.server_dir = SERVER_DIR
        self.venv_dir = VENV_DIR
        self.env_file = ENV_FILE
        self.python_exec = self.venv_dir / "bin" / "python3"
        self.pip_exec = self.venv_dir / "bin" / "pip"
    
    def log(self, stage, msg, status="ℹ️ "):
        """打印日志"""
        print(f"{status} [{stage}] {msg}")
    
    def check_environment(self):
        """检查环境"""
        print("\n" + "="*70)
        print("🔍 环境检查")
        print("="*70 + "\n")
        
        # 检查 Python
        self.log("Python", f"版本 {sys.version.split()[0]}", "✓")
        
        # 检查虚拟环境
        if self.venv_dir.exists():
            self.log("虚拟环境", "已存在", "✓")
        else:
            self.log("虚拟环境", "不存在（将被创建）", "⚠️ ")
        
        # 检查依赖文件
        req_file = self.server_dir / "requirements.txt"
        if req_file.exists():
            self.log("依赖文件", "requirements.txt 已存在", "✓")
        else:
            self.log("依赖文件", "requirements.txt 不存在", "❌")
            return False
        
        # 检查 .env 文件
        if self.env_file.exists():
            self.log("配置文件", ".env 已存在", "✓")
            load_dotenv(self.env_file)
            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if api_key and api_key.startswith("sk-"):
                self.log("API Key", "已配置", "✓")
            else:
                self.log("API Key", "未正确配置（使用 demo 模式）", "⚠️ ")
        else:
            self.log("配置文件", ".env 不存在（使用默认配置）", "⚠️ ")
        
        # 检查数据库
        if DB_FILE.exists():
            size_mb = DB_FILE.stat().st_size / (1024*1024)
            self.log("数据库", f"ai_child.db 已存在 ({size_mb:.1f}MB)", "✓")
        else:
            self.log("数据库", "ai_child.db 不存在（将自动创建）", "ℹ️ ")
        
        return True
    
    def setup_venv(self):
        """设置虚拟环境"""
        print("\n" + "="*70)
        print("⚙️  设置虚拟环境")
        print("="*70 + "\n")
        
        if self.venv_dir.exists():
            self.log("虚拟环境", "已存在，跳过创建", "✓")
        else:
            self.log("虚拟环境", "创建中...", "⏳")
            try:
                subprocess.run(
                    [sys.executable, "-m", "venv", str(self.venv_dir)],
                    check=True,
                    capture_output=True
                )
                self.log("虚拟环境", "创建成功", "✓")
            except subprocess.CalledProcessError as e:
                self.log("虚拟环境", f"创建失败: {e}", "❌")
                return False
        
        # 安装依赖
        self.log("依赖", "安装中...", "⏳")
        try:
            subprocess.run(
                [str(self.pip_exec), "install", "-q", "-r", 
                 str(self.server_dir / "requirements.txt")],
                check=True,
                capture_output=True
            )
            self.log("依赖", "安装成功", "✓")
        except subprocess.CalledProcessError as e:
            self.log("依赖", f"安装失败: {e}", "❌")
            return False
        
        return True
    
    def create_env_template(self):
        """创建 .env 模板"""
        if not self.env_file.exists():
            self.log("配置", "创建 .env.example 模板...", "⏳")
            template = """# AI Child 配置文件
# 复制为 .env 并填入你的 API Key

# OpenAI API Key (必需)
OPENAI_API_KEY=sk-your-api-key-here

# 可选配置（有默认值）
OPENAI_MODEL=gpt-4o
DATABASE_URL=sqlite+aiosqlite:///./ai_child.db
MEMORY_CONTEXT_TURNS=20
PROACTIVE_QUESTION_INTERVAL=2
SLEEP_ENABLED=true
RESEARCH_ENABLED=true
"""
            env_example = self.server_dir / ".env.example"
            env_example.write_text(template)
            self.log("配置", ".env.example 已创建，作为参考使用", "ℹ️ ")
    
    def start_server(self):
        """启动服务器"""
        print("\n" + "="*70)
        print("🚀 启动 AI Child 服务器")
        print("="*70 + "\n")
        
        self.log("服务器", "在 http://localhost:8000 启动中...", "⏳")
        print("\n" + "-"*70)
        print("💡 提示：")
        print("  📚 API 文档:        http://localhost:8000/docs")
        print("  💚 健康检查:         http://localhost:8000/health")
        print("  👤 AI 配置:         http://localhost:8000/profile")
        print("\n  按 Ctrl+C 停止服务器")
        print("-"*70 + "\n")
        
        try:
            os.chdir(self.server_dir)
            
            # 设置环境变量
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            
            # 启动 uvicorn
            result = subprocess.run(
                [
                    str(self.python_exec), "-m", "uvicorn",
                    "main:app",
                    "--host", "0.0.0.0",
                    "--port", "8000",
                    "--reload"
                ],
                env=env
            )
            
            return result.returncode == 0
        except KeyboardInterrupt:
            self.log("服务器", "已停止", "⏹️ ")
            return True
        except Exception as e:
            self.log("服务器", f"启动失败: {e}", "❌")
            return False
    
    def run_checks(self):
        """运行检查"""
        print("\n" + "="*70)
        print("✅ 检查完成")
        print("="*70 + "\n")
        
        if not self.env_file.exists():
            print("""
📝 【需要配置 API Key】

1. 获取 OpenAI API Key:
   https://platform.openai.com/api-keys

2. 在 server/.env 中添加:
   OPENAI_API_KEY=sk-your-key

3. 或直접创建文件:
   echo "OPENAI_API_KEY=sk-your-key" > server/.env
            """)
        else:
            print("✓ 环境已配置，准备启动")
        
        print("\n运行以下命令启动：")
        print(f"\n  python start_ai_child.py --server\n")
    
    def reset_database(self):
        """重置数据库"""
        if DB_FILE.exists():
            self.log("数据库", "删除旧数据库...", "⏳")
            DB_FILE.unlink()
            
            # 删除相关的锁文件
            for db_file in self.server_dir.glob("ai_child.db*"):
                db_file.unlink()
            
            self.log("数据库", "已重置", "✓")
        else:
            self.log("数据库", "不存在，无需重置", "ℹ️ ")
    
    def run(self, mode="full"):
        """运行启动流程"""
        if mode == "check":
            return self.check_environment()
        elif mode == "reset":
            self.reset_database()
            return True
        elif mode == "server":
            # 快速启动：检查 + 启动
            if not self.check_environment():
                print("\n⚠️  环境检查失败，请检查上述错误")
                return False
            
            if not self.setup_venv():
                print("\n⚠️  虚拟环境设置失败")
                return False
            
            self.create_env_template()
            self.start_server()
            return True
        else:
            # 完整流程
            print("\n" + "="*70)
            print("🎉 AI Child 启动向导")
            print("="*70)
            
            if not self.check_environment():
                print("\n⚠️  环境检查失败!")
                return False
            
            if not self.setup_venv():
                print("\n⚠️  设置失败!")
                return False
            
            self.create_env_template()
            self.run_checks()
            return True

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="AI Child 启动管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python start_ai_child.py              # 完整启动流程
  python start_ai_child.py --server     # 启动服务器
  python start_ai_child.py --check      # 检查环境
  python start_ai_child.py --reset      # 重置数据库
        """
    )
    
    parser.add_argument(
        "--server", action="store_true",
        help="启动服务器"
    )
    parser.add_argument(
        "--check", action="store_true",
        help="检查环境"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="重置数据库（谨慎使用）"
    )
    parser.add_argument(
        "--language", 
        choices=["en-US", "zh-CN"],
        default="en-US",
        help="首选语言 / Preferred language (default: en-US)"
    )
    parser.add_argument(
        "--export-personality",
        action="store_true",
        help="启动前导出人格档案 / Export personality before startup"
    )
    
    args = parser.parse_args()
    
    startup = Startup()
    
    if args.server:
        success = startup.run("server")
    elif args.check:
        success = startup.run("check")
    elif args.reset:
        success = startup.run("reset")
    else:
        success = startup.run("full")
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
