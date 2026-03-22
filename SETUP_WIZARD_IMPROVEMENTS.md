# 🔧 Setup Wizard 改进说明

## 解决的问题

### 1️⃣ 模型迁移问题
**问题**: GGUF文件迁移到Ollama目录后，`ollama list`看不到模型

**解决方案**:
- 向导会自动检测本地GGUF文件
- 使用 `ollama create` 命令注册模型
- 创建必要的Modelfile来让Ollama正式管理模型
- 支持的本地模型:
  - `qwen-local` - Qwen 3.5-9B
  - `gemma-local` - Gemma-3-12B
  - `huihui-qwen-local` - Huihui Qwen VL-8B

### 2️⃣ 加强用户引导

**改进内容**:

#### 交互式提示增强
- ✅ 每个选项配有说明文本（为什么选这个选项）
- ✅ 建议默认项用绿色箭头标记
- ✅ 帮助提示显示在输入前（看例子、冠口诀）
- ✅ 更详细的错误消息

示例：
```
工作流程学习：
  → 1. Ollama (Local, Recommended - No API key needed)
      Your own models, no API key needed, fast startup
    2. OpenAI (Cloud, Requires API key)
      Use powerful cloud models, requires API key
    3. DashScope/阿里云 (Cloud, Requires API key)
      Use Alibaba Qwen models, requires API key

Choose (1-3) [1]:
```

#### 详细的步骤说明
- 📱 设置Telegram: 显示完整的@BotFather流程
- 🎮 设置QQ: 显示go-cqhttp安装步骤
- ⚙️ 服务器设置: 解释端口、时区、睡眠时间

#### 实时验证
- ✅ 检查Ollama安装状态
- ✅ 自动尝试连接到Ollama服务收
- ✅ 列出已有模型供选择
- ✅ 验证所有依赖包

#### 智能模型管理
- 🔍 自动扫描本地GGUF文件
- 📋 显示模型大小和名称
- 👁️ 提示注册本地模型
- 🎯 执行`ollama create`自动完成注册

#### 更好的最后指导
设置完成后显示：
- 逐步启动过程
- 每个终端的确切命令
- 访问URL和API文档位置
- 提醒.env文件安全性

## 新增功能

### `setup_ollama_models()` 函数
```python
# 自动发现和注册本地GGUF模型
setup_ollama_models()
# 输出: 检测到3个本地模型，提示注册
```

### 改进的提示函数
```python
# prompt_choice 现在支持描述
prompt_choice(
    "Which provider?",
    choices=["Option 1", "Option 2"],
    descriptions=["Benefit 1", "Benefit 2"]  # ← 新增
)

# prompt_text 现在支持帮助文本
prompt_text(
    "Enter your API key",
    help_text="Found in: https://platform.openai.com/api-keys"  # ← 新增
)
```

## 使用指南

### 快速启动（30秒）
```bash
./setup.sh
# 或
python3 setup_wizard.py
```

### 工作流程
1. **向导会问**: "什么是LLM提供商？" → 选择 Ollama ✓
2. **向导会做**:
   - ✅ 检测Ollama安装
   - ✅ 连接测试
   - ✅ 扫描本地模型
   - ✅ **自动注册模型** ← 新功能！
3. **向导会询问**: 其他配置（机器人、时区等）
4. **向导会生成**: `.env` 文件
5. **向导会显示**: 启动命令

### 模型注册示例

在向导中:
```
📚 Available Ollama models:
   qwen-local       4.2 GB
   gemma-local      5.1 GB
   huihui-qwen-local 8.7 GB

Which Ollama model would you like to use? [qwen2]: qwen-local
```

然后在Ollama中:
```bash
ollama list
```

输出:
```
NAME             	ID          	SIZE    	MODIFIED
qwen-local       	abc123...   	4.2 GB  	Now
gemma-local      	def456...   	5.1 GB  	Now
huihui-qwen-local	ghi789...   	8.7 GB  	1 second ago
```

## 技术细节

### Modelfile 自动生成
```dockerfile
FROM /path/to/model.gguf
TEMPLATE "[INST] {{ .Prompt }} [/INST]"
SYSTEM You are a helpful AI assistant.
```

### 模型注册命令
```bash
ollama create qwen-local -f /tmp/Modelfile-qwen-local
```

## 测试步骤

1. 运行向导
2. 选择Ollama
3. 让向导检测和注册本地模型
4. 完成后运行: `ollama list`
5. 验证模型已显示

## 下一步

设置完成后，按照向导的"What's Next"步骤：

```bash
# Terminal 1: Ollama
ollama serve

# Terminal 2: AI Child Server
cd server && python3 main.py

# Terminal 3: Bot
cd bot && python3 main.py qq
```

访问: http://localhost:8000
