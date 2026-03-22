#!/bin/bash
# AI Child 一键启动脚本 v2.0
# 提供所有启动命令和诊断信息

set -e

PROJECT_DIR="/Volumes/mac第二磁盘/ai-child"
cd "$PROJECT_DIR"

clear

cat << 'EOF'
╔════════════════════════════════════════════════════════════════╗
║                   🚀 AI Child 快速启动                          ║
║                                                                ║
║        Local Ollama + QQ Bot + Web UI                         ║
╚════════════════════════════════════════════════════════════════╝

EOF

# 检查环境
echo "📋 环境检查..."
echo ""

# 检查Ollama
if command -v ollama &> /dev/null; then
    OLLAMA_VERSION=$(ollama --version 2>/dev/null || echo "unknown")
    echo "✅ Ollama 已安装"
else
    echo "❌ Ollama 未安装"
    echo "   请访问: https://ollama.com/download"
    exit 1
fi

# 检查Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✅ Python 已安装 ($PYTHON_VERSION)"
else
    echo "❌ Python3 未安装"
    exit 1
fi

# 检查本地模型
echo ""
echo "📦 检查本地模型..."
MODELS_DIR="/Volumes/mac第二磁盘/ollama/models"
if [ -d "$MODELS_DIR" ]; then
    GGUF_COUNT=$(find "$MODELS_DIR" -name "*.gguf" 2>/dev/null | wc -l)
    if [ "$GGUF_COUNT" -gt 0 ]; then
        echo "✅ 找到 $GGUF_COUNT 个本地 GGUF 模型"
        find "$MODELS_DIR" -name "*.gguf" 2>/dev/null | while read file; do
            SIZE=$(ls -lh "$file" | awk '{print $5}')
            DIRNAME=$(basename "$(dirname "$file")")
            echo "   • $DIRNAME ($SIZE)"
        done
    else
        echo "⚠️  未找到本地模型，但可以使用官方模型"
    fi
else
    echo "⚠️  模型目录不存在: $MODELS_DIR"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "🎯 启动方式 (选择一种)"
echo "════════════════════════════════════════════════════════════════"
echo ""

cat << 'OPTS'
【选项 1】自动启动 Ollama（推荐新手）
────────────────────────────────────────
运行此命令（需要 Mac 用户登录）:

    open -a /Applications/Ollama.app

或在终端运行:

    ollama serve


【选项 2】完整手动启动（推荐体验用户）
────────────────────────────────────────
分别在三个终端运行：

终端 1 - 启动 Ollama:
    ┌─────────────────────────────────────┐
    │ ollama serve                        │
    └─────────────────────────────────────┘
    等待看到: "Listening on [::]:11434"

终端 2 - 启动 AI Child 服务器:
    ┌─────────────────────────────────────┐
    │ cd /Volumes/mac第二磁盘/ai-child/server && python3 main.py
    └─────────────────────────────────────┘
    等待看到: "Uvicorn running on"

终端 3 - 启动 QQ 机器人:
    ┌─────────────────────────────────────┐
    │ cd /Volumes/mac第二磁盘/ai-child/bot && python3 main.py qq
    └─────────────────────────────────────┘
    等待看到: "QQ adapter running"


【选项 3】启动所有机器人（支持QQ+Telegram）
────────────────────────────────────────
在终端 3 改为:
    cd /Volumes/mac第二磁盘/ai-child/bot && python3 main.py


【选项 4】只启动 Telegram 机器人
────────────────────────────────────────
在终端 3 改为:
    cd /Volumes/mac第二磁盘/ai-child/bot && python3 main.py telegram

OPTS

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "✨ 启动后"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "🌐 打开浏览器访问 Web UI:"
echo "   http://localhost:8000"
echo ""
echo "📚 查看 API 文档:"
echo "   http://localhost:8000/docs"
echo ""
echo "💬 测试 QQ 机器人:"
echo "   在 QQ 中发送消息"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "🔧 配置文件位置"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "📝 服务器配置:"
echo "   $PROJECT_DIR/server/.env"
echo ""
echo "🤖 机器人配置:"
echo "   $PROJECT_DIR/bot/.env"
echo ""
echo "💾 这些文件被 .gitignore 保护，请勿上传到 GitHub"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "📞 故障排查"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "问题: Ollama 连接失败"
echo "  → 确保运行了 'ollama serve'"
echo "  → 等待 30 秒让 Ollama 完全启动"
echo ""
echo "问题: 服务器无法启动"
echo "  → 检查端口 8000 是否被占用"
echo "  → 运行: lsof -i :8000"
echo ""
echo "问题: 模型看不到"
echo "  → 运行: ollama list"
echo "  → 如果为空，运行: python3 setup_wizard.py 注册本地模型"
echo ""
echo "问题: QQ 机器人不响应"
echo "  → 检查 .env 中的 QQ_API_URL 配置"
echo "  → 确保 go-cqhttp 正在运行 (如果使用 QQ)"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "💡 快速命令"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "# 诊断本地模型"
echo "  ./test_ollama_models.sh"
echo ""
echo "# 重新配置系统"
echo "  ./setup.sh"
echo ""
echo "# 查看 API 文档"
echo "  curl http://localhost:8000/docs"
echo ""
echo "# 检查服务器状态"
echo "  curl http://localhost:8000/health"
echo ""

echo "════════════════════════════════════════════════════════════════"
echo "✅ 一切就绪！请按照上面的选项启动系统"
echo "════════════════════════════════════════════════════════════════"
echo ""
