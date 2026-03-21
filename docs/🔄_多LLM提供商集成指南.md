# 🔄 多 LLM 提供商集成指南

## 现状总结

✅ **已完成**：
- LLM 工厂类 (`server/ai/llm_provider.py`) - 已创建
- 配置扩展 (`server/config.py`) - 已更新
- 依赖安装 (`server/requirements.txt`) - 已更新
- 应用启动 (`server/main.py`) - 已初始化

❌ **待完成**：
- 修改 5 个调用 OpenAI 的模块使用工厂

---

## 模块修改清单

| 模块 | 文件 | 优先级 | 调用点 | 状态 |
|------|------|--------|--------|------|
| 聊天核心 | `server/ai/child.py` | P0 | 3 处 | ⏳ 待改 |
| 研究引擎 | `server/ai/researcher.py` | P1 | 2 处 | ⏳ 待改 |
| 多模态 | `server/ai/multimodal.py` | P2 | 3 处 | ⏳ 待改 |
| 名字提取 | `server/ai/profile.py` | P3 | 1 处 | ⏳ 待改 |
| 睡眠管理 | `server/ai/sleep.py` | P3 | 2 处 | ⏳ 待改 |

---

## 修改模式

### 模式 A：标准聊天补全

**之前**（使用 OpenAI 直接）：
```python
from openai import AsyncOpenAI
client = AsyncOpenAI(api_key=settings.openai_api_key)

response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[...],
    temperature=0.7,
    max_tokens=100
)

# 处理响应
if response.choices[0].finish_reason == "tool_calls":
    for tc in response.choices[0].message.tool_calls:
        ...
else:
    content = response.choices[0].message.content
```

**之后**（使用 LLM 工厂）：
```python
from ai.llm_provider import chat_completion

llm_response = await chat_completion(
    messages=[...],
    temperature=0.7,
    max_tokens=100
)

# 处理响应
if llm_response.tool_calls:
    for tool_call in llm_response.tool_calls:
        # tool_call.tool_name
        # tool_call.arguments
        ...
else:
    content = llm_response.content
```

**关键差异**：
- 不需要导入 AsyncOpenAI
- 直接调用 `chat_completion()` 便捷函数
- 响应格式统一（`ChatResponse` 对象）
- 工具调用格式简化

---

### 模式 B：音频处理

**之前**（Whisper 转录）：
```python
response = await client.audio.transcriptions.create(
    model="whisper-1",
    file=audio_file,
    language="zh"
)
text = response.text
```

**之后**：
```python
from ai.llm_provider import transcribe_audio

text = await transcribe_audio(
    audio_file_path,
    language="zh"
)
```

---

### 模式 C：文字转语音

**之前**：
```python
response = await client.audio.speech.create(
    model="tts-1",
    voice="alloy",
    input=text
)
audio_bytes = response.content
```

**之后**：
```python
from ai.llm_provider import text_to_speech

audio_bytes = await text_to_speech(text, voice="alloy")
```

---

## 分步修改指南

### 🟢 步骤 1：修改 `server/ai/child.py`（最关键）

**改动概述**：
- 删除 `from openai import AsyncOpenAI` 和 `client = ...`
- 添加 `from ai.llm_provider import chat_completion`
- 替换 3 处 `client.chat.completions.create()` 调用

**具体修改**：

**修改点 1**（第 40 行）：
```python
# ❌ 删除这行
# from openai import AsyncOpenAI
# client = AsyncOpenAI(api_key=settings.openai_api_key)

# ✅ 添加这行
from ai.llm_provider import chat_completion
```

**修改点 2**（第 212 行 - 主聊天循环）：
```python
# ❌ 之前
response = await client.chat.completions.create(
    model=settings.openai_model,
    messages=messages,
    tools=tool_defs,
    temperature=0.7,
    max_tokens=8000,
)
choice = response.choices[0]
if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
    messages.append(_assistant_message_dict(choice.message))
    for tc in choice.message.tool_calls:
        # ... 处理工具调用

# ✅ 之后
llm_response = await chat_completion(
    messages=messages,
    model=settings.openai_model,
    temperature=0.7,
    max_tokens=8000,
    tools=tool_defs
)

if llm_response.tool_calls:
    # 构建回复消息
    messages.append({
        "role": "assistant",
        "content": llm_response.content,
        "tool_calls": [
            {
                "type": "function",
                "function": {
                    "name": tc.tool_name,
                    "arguments": json.dumps(tc.arguments)
                }
            }
            for tc in llm_response.tool_calls
        ]
    })
    
    for tc in llm_response.tool_calls:
        try:
            result = await dispatch_tool(
                session,
                tc.tool_name,
                tc.arguments,
                code_exec_timeout=settings.code_exec_timeout,
            )
            messages.append({
                "role": "tool",
                "tool_call_id": tc.tool_name,  # 注意：简化处理
                "content": result,
            })
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
else:
    reply_text = llm_response.content or ""
    break
```

**修改点 3**（第 290 行 - 如果还有）和**第 4**（第 325 行 - `_generate_proactive_question`）：
类似的替换模式。

---

### 🟡 步骤 2：修改 `server/ai/researcher.py`

```python
# ❌ 删除
from openai import AsyncOpenAI
client = AsyncOpenAI(api_key=settings.openai_api_key)

# ✅ 添加
from ai.llm_provider import chat_completion

# 替换所有 client.chat.completions.create() 调用
# 最多 2 处
```

**具体搜索到的调用**：
- 生成搜索查询
- 总结搜索结果

都用相同的模式替换。

---

### 🟠 步骤 3：修改 `server/ai/multimodal.py`

```python
# ❌ 删除
from openai import AsyncOpenAI
client = AsyncOpenAI(api_key=settings.openai_api_key)

# ✅ 添加
from ai.llm_provider import chat_completion, transcribe_audio, text_to_speech

# 替换调用
# - chat.completions.create() → chat_completion()
# - audio.transcriptions.create() → transcribe_audio()
# - audio.speech.create() → text_to_speech()
```

---

### 🟡 步骤 4：修改 `server/ai/profile.py`

```python
# ❌ 删除
from openai import AsyncOpenAI
client = AsyncOpenAI(api_key=settings.openai_api_key)

# ✅ 添加
from ai.llm_provider import chat_completion

# 替换 1 处 client.chat.completions.create() 调用
```

---

### 🟡 步骤 5：修改 `server/ai/sleep.py`

```python
# ❌ 删除
from openai import AsyncOpenAI
client = AsyncOpenAI(api_key=settings.openai_api_key)

# ✅ 添加
from ai.llm_provider import chat_completion

# 替换 2 处 client.chat.completions.create() 调用
```

---

## 配置使用方法

### 使用 OpenAI（默认）

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
```

或在 `.env` 文件中：
```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

---

### 使用百炼（DashScope）

```bash
export LLM_PROVIDER=dashscope
export DASHSCOPE_API_KEY=sk-1435063985134058862382c9714bab35
```

或在 `.env` 文件中：
```
LLM_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-1435063985134058862382c9714bab35
DASHSCOPE_MODEL=qwen3.5-35b-a3b
```

---

## 启动步骤

### 第一次设置

```bash
# 1. 安装依赖
cd server
pip install -r requirements.txt

# 2. 更新 OpenAI 会话（如有数据库迁移需要）
# （可选，如无迁移则跳过）

# 3. 配置 .env
cat > .env <<'EOF'
LLM_PROVIDER=dashscope
DASHSCOPE_API_KEY=sk-1435063985134058862382c9714bab35
DASHSCOPE_MODEL=qwen3.5-35b-a3b
EOF

# 4. 启动服务器
python main.py
```

### 验证 LLM 切换

```bash
# 查看日志首行
# 应该看到类似：
# ✅ DashScope (百炼) provider initialized
# 🚀 Using DashScope (百炼) as LLM provider
```

---

## ⚠️ 百炼特有限制

### 音频处理

百炼 API 目前不支持 Whisper 类似的音频转录和 TTS 服务。**解决方案**：

```python
# 在 multimodal.py 中
if settings.llm_provider == "dashscope":
    # 音频处理回退到 OpenAI（如果需要）
    from ai.llm_provider import OpenAIProvider
    audio_provider = OpenAIProvider(
        api_key=settings.openai_api_key  # 需要同时配置 OpenAI API Key
    )
    text = await audio_provider.transcribe_audio(file_path)
else:
    # 使用当前提供商
    text = await transcribe_audio(file_path)
```

### 工具调用

百炼的工具调用 API 与 OpenAI 可能略有不同。如果遇到工具调用问题，可能需要：
1. 调整提示词强调工具使用
2. 检查工具定义格式是否兼容

---

## 测试清单

- [ ] 服务器启动，LLM provider 初始化成功
- [ ] 发送一条文本消息，获得正常回复
- [ ] 发送一条图片，AI 能描述图片
- [ ] AI 主动提问（检查 [QUESTION:...] 格式）
- [ ] `/teach` 命令保存知识
- [ ] 网络搜索工具能正常调用
- [ ] 切换回 OpenAI，确保兼容性

---

## 常见问题

**Q: 切换 LLM 后需要重新启动吗？**  
A: 是的，需要重新启动服务器以加载新的配置。

**Q: 能否在同一个系统中混合使用两个提供商？**  
A: 不能。系统一次只支持一个 LLM 提供商。

**Q: 百炼 API 出现错误怎么办？**  
A: 检查日志中的具体错误信息，通常是 API Key 错误或配额限制。

**Q: 响应质量能否匹敌 GPT-4o？**  
A: 取决于你选择的模型。通用大模型通常比 GPT-4o 弱，但特定领域可能更强。

---

## 迁移计划

1. **第一阶段（现在）**：部署工厂层 ✅
2. **第二阶段（1 小时）**：修改 5 个模块
3. **第三阶段（30 分钟）**：测试验证
4. **第四阶段（可选）**：旧代码清理（如确认新方案稳定）

---

## 后续优化

- [ ] 添加模型性能对比测试
- [ ] 实现自动降级（百炼不支持的功能回退到 OpenAI）
- [ ] 支持多模型并行调用（A/B 测试）
- [ ] 成本监控和优化建议

