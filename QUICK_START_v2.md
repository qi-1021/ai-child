# 🚀 快速启动指南 v2.0

> 更强的引导 + 自动模型注册 ✨

## 第一次使用？使用向导（推荐）

```bash
# 进入项目目录
cd /Volumes/mac第二磁盘/ai-child

# 运行交互式设置向导
./setup.sh

# 或直接用Python
python3 setup_wizard.py
```

向导会自动帮你完成：
- ✅ 检查Ollama安装
- ✅ **自动发现并注册本地GGUF模型**
- ✅ 配置聊天机器人（QQ、Telegram）
- ✅ 生成 `.env` 配置文件
- ✅ 验证所有依赖

## 设置后：启动系统（三个终端）

### 终端 1️⃣：启动Ollama
```bash
ollama serve
```
等待看到: `Listening on [::]:11434`

### 终端 2️⃣：启动AI Child服务器
```bash
cd /Volumes/mac第二磁盘/ai-child/server
python3 main.py
```
等待看到: `Uvicorn running on http://0.0.0.0:8000`

### 终端 3️⃣：启动机器人

**仅QQ机器人:**
```bash
cd /Volumes/mac第二磁盘/ai-child/bot
python3 main.py qq
```

**仅Telegram:**
```bash
python3 main.py telegram
```

**所有机器人:**
```bash
python3 main.py
```

## 访问系统

- 🌐 **Web UI**: http://localhost:8000
- 📚 **API文档**: http://localhost:8000/docs
- 💬 **QQ**: 在QQ中与AI聊天
- 📱 **Telegram**: 在Telegram中与AI聊天

## 测试本地模型

如果看不到你的本地模型，运行诊断脚本：

```bash
./test_ollama_models.sh
```

这会显示：
- ✓ Ollama连接状态
- ✓ 扫描的GGUF文件
- ✓ 文件大小和位置

## 常见问题

### Q: "Ollama is not running"
```bash
# 新开一个终端运行:
ollama serve
```

### Q: "Cannot connect to server"
```bash
# 检查服务器是否运行:
curl http://localhost:8000/health

# 如果不行，启动它:
cd server && python3 main.py
```

### Q: 为什么`ollama list`看不到我的模型？
**自动解决:** 向导现在会自动注册模型！
```bash
# 如果还是看不到，运行诊断:
./test_ollama_models.sh

# 然后再次运行向导注册:
python3 setup_wizard.py
```

### Q: 如何添加新模型？
```bash
# 拉取官方模型
ollama pull llama2
ollama pull mistral

# 或使用本地GGUF文件
ollama create my-model -f /path/to/Modelfile
```

### Q: 如何改变模型？
编辑配置文件:
```bash
# 编辑 server/.env
# 改变: OLLAMA_MODEL=qwen-local
# 为:    OLLAMA_MODEL=另一个模型名
```

## 配置文件位置

```
ai-child/
├── server/.env          ← 服务器配置（安全）
├── bot/.env             ← 机器人配置（安全）
├── .gitignore           ← 排除上述文件
├── setup_wizard.py      ← 交互式设置
├── setup.sh             ← 设置启动器
├── test_ollama_models.sh ← 诊断工具
└── SETUP_WIZARD_IMPROVEMENTS.md ← 详细说明
```

## 本地可用的模型

设置向导自动发现这些模型：

| 模型名 | 大小 | 用途 | 注册名 |
|--------|------|------|--------|
| Qwen 3.5-9B | 4.2GB | 通用对话 | `qwen-local` |
| Gemma-3-12B | 5.1GB | 高质量回复 | `gemma-local` |
| Huihui Qwen VL-8B | 8.7GB | 图片识别 | `huihui-qwen-local` |

## 脚本说明

### `setup.sh`
- 新用户首选
- 自动找到Python 3
- 运行setup_wizard.py

### `setup_wizard.py`
- 完整的交互式向导
- 模型注册功能
- 依赖验证
- 生成.env文件

### `test_ollama_models.sh`
- 诊断工具
- 检查Ollama状态
- 列出可用的GGUF文件

## 工作流程图

```
┌─────────────────────┐
│  第一次运行？        │
└──────────┬──────────┘
           │
           ▼
    ┌────────────┐
    │ ./setup.sh │ ← 强烈推荐
    └──────┬─────┘
           │
           ├─ 检查Ollama ✓
           ├─ 扫描模型 ✓
           ├─ 注册模型 ✓ ← 新功能！
           ├─ 配置机器人 ✓
           └─ 生成.env ✓
           │
           ▼
    ┌─────────────────┐
    │ 启动3个终端:    │
    ├─ ollama serve  │
    ├─ python3 main  │ (server)
    └─ python3 main  │ (bot)

    访问: localhost:8000
```

## 需要帮助？

1. 📖 查看 `SETUP.md` - 详细设置说明
2. 🔍 查看 `SETUP_WIZARD_IMPROVEMENTS.md` - 技术细节
3. 🧪 运行 `./test_ollama_models.sh` - 诊断问题
4. ❓ 查看 GitHub Issues - 提问社区

---

**版本:** 2.0
**最后更新:** 2024-03-22
**特性:** 自动模型注册 + 加强引导

Happy chatting! 🎉
