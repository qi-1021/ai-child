#!/bin/bash
# AI Child 启动脚本 (macOS/Linux)
# 使用方式: bash quick_start.sh

set -e

PROJECT_ROOT="/Volumes/mac第二磁盘/ai-child"
SERVER_DIR="$PROJECT_ROOT/server"

echo "╔═══════════════════════════════════════════════════════╗"
echo "║      🚀 AI Child 快速启动脚本                         ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""

# 检查 Python 版本
echo "📌 [步骤 1/5] 检查 Python 版本..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "   ✓ Python $python_version"
echo ""

# 检查/创建虚拟环境
echo "📌 [步骤 2/5] 检查虚拟环境..."
if [ ! -d "$SERVER_DIR/.venv" ]; then
    echo "   ⚙️  创建虚拟环境..."
    cd "$SERVER_DIR"
    python3 -m venv .venv
    echo "   ✓ 虚拟环境已创建"
else
    echo "   ✓ 虚拟环境已存在"
fi
echo ""

# 激活虚拟环境
echo "📌 [步骤 3/5] 激活虚拟环境..."
source "$SERVER_DIR/.venv/bin/activate"
echo "   ✓ 虚拟环境已激活"
echo ""

# 安装依赖
echo "📌 [步骤 4/5] 检查依赖..."
pip install -q -r "$SERVER_DIR/requirements.txt" 2>/dev/null || true
echo "   ✓ 依赖已安装"
echo ""

# 检查或创建 .env 文件
echo "📌 [步骤 5/5] 检查配置文件..."
if [ ! -f "$SERVER_DIR/.env" ]; then
    echo "   ⚠️  .env 文件不存在，使用默认配置"
    echo "   📝 提示：如需使用 OpenAI API，请创建 $SERVER_DIR/.env"
    echo "   📝 示例："
    echo "      OPENAI_API_KEY=sk-..."
else
    echo "   ✓ .env 文件已存在"
fi
echo ""

echo "╔═══════════════════════════════════════════════════════╗"
echo "║             ✅ 启动准备完成！                        ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""
echo "🚀 启动服务器："
echo ""
echo "   cd $PROJECT_ROOT/server"
echo "   source .venv/bin/activate"
echo "   python main.py"
echo ""
echo "或使用 uvicorn 直接启动："
echo ""
echo "   uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "服务器启动后，访问："
echo "   📚 API 文档: http://localhost:8000/docs"
echo "   💚 健康检查: http://localhost:8000/health"
echo ""
