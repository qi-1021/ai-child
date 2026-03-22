#!/bin/bash
# =========================================================================
# AI Child 完整启动脚本 (带 Ollama 本地模型)
# =========================================================================
# 用法: chmod +x start_ai_child.sh && ./start_ai_child.sh

set -e

echo "=========================================="
echo "🚀 AI Child 系统启动"
echo "=========================================="
echo ""

# 颜色代码
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查环境
echo "${BLUE}📋 系统检查...${NC}"

# 检查 Ollama
if ! command -v ollama &> /dev/null; then
    echo "${YELLOW}⚠️  Ollama 未安装。请访问 https://ollama.com 安装${NC}"
    exit 1
fi
echo "${GREEN}✅ Ollama 已安装${NC}"

# 检查模型目录
if [ ! -d "/Volumes/mac第二磁盘/ollama/models" ]; then
    echo "${YELLOW}⚠️  Ollama 模型目录不存在${NC}"
    exit 1
fi
echo "${GREEN}✅ Ollama 模型目录已确认${NC}"

# 检查 AI Child
if [ ! -d "/Volumes/mac第二磁盘/ai-child" ]; then
    echo "${YELLOW}⚠️  AI Child 项目目录不存在${NC}"
    exit 1
fi
echo "${GREEN}✅ AI Child 项目已确认${NC}"

echo ""
echo "=========================================="
echo "🎯 三步启动系统"
echo "=========================================="
echo ""

echo "${BLUE}1️⃣  启动 Ollama 守护进程${NC}"
echo "   在新终端运行:"
echo "   ${YELLOW}ollama serve${NC}"
echo ""

echo "${BLUE}2️⃣  启动 AI Child 服务器${NC}"
echo "   在新终端运行:"
echo "   ${YELLOW}cd /Volumes/mac第二磁盘/ai-child/server${NC}"
echo "   ${YELLOW}/opt/homebrew/opt/python@3.12/bin/python3.12 main.py${NC}"
echo ""

echo "${BLUE}3️⃣  启动 QQ 机器人${NC}"
echo "   在新终端运行:"
echo "   ${YELLOW}cd /Volumes/mac第二磁盘/ai-child/bot${NC}"
echo "   ${YELLOW}/opt/homebrew/opt/python@3.12/bin/python3.12 main.py qq${NC}"
echo ""

echo "=========================================="
echo "✨ 可用的资源"
echo "=========================================="
echo ""
echo "🌐 Web UI (对话页面):"
echo "   ${BLUE}http://localhost:8000${NC}"
echo ""
echo "📚 API 文档:"
echo "   ${BLUE}http://localhost:8000/docs${NC}"
echo ""
echo "📂 Ollama 模型位置:"
echo "   ${YELLOW}/Volumes/mac第二磁盘/ollama/models${NC}"
echo ""
echo "📦 已迁移的模型:"
echo "   • Qwen 3.5-9B (推荐中文)"
echo "   • Gemma-3-12B (Abliterated)"
echo "   • Huihui Qwen VL-8B (视觉模型)"
echo ""

echo "=========================================="
echo "🎮 使用方式"
echo "=========================================="
echo ""
echo "在 QQ 中直接对话，或访问 Web UI 进行多功能操作:"
echo ""
echo "✓ 纯文本对话"
echo "✓ 图片识别与分析"
echo "✓ 教导 AI 新知识"
echo "✓ 查看 AI 的主动问题"
echo "✓ 查看学到的知识库"
echo ""
