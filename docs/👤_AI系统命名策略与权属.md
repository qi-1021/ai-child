# 👤 AI 系统命名策略与权属

## 核心原则

**命名权 100% 属于用户（教导者）**

- ❌ 不在文档中预设名字
- ❌ 不在代码中硬编码名字  
- ✅ 系统在首次启动时主动询问用户
- ✅ 用户可随时修改命名
- ✅ 尊重用户对 AI 的定义权

---

## 为什么不能预命名

### 理由1️⃣：育儿初心
在真实的教养关系中，**父母/教育者给孩子命名**，这是关系中的权力体现和情感投入。  
如果系统预设名字（如"小智"），违背了这一点——用户失去了定义 AI 身份的机会。

---

### 理由2️⃣：多元化需求
不同用户对 AI 的定位不同：
- 有人想要"学习助手"→ 可能叫"助研"、"思考者"
- 有人想要"陪伴角色"→ 可能叫"朋友"、"小伙伴"
- 有人想要"中立工具"→ 可能叫"系统"、"机器"
- 不同文化　→ 中文、英文、其他语言都支持

---

### 理由3️⃣：长期关系的发展
AI 的名字可能随关系演进而改变：
- 初期："小助手"（陌生感）
- 中期："朋友名字"（熟悉感）
- 深度学习后：可能需要更成熟的名字

允许用户修改命名权，是尊重这种关系的动态性。

---

## 实施方案

### 阶段1️⃣：首次启动时主动询问

**触发条件**：AI 档案中 `name` 字段为 NULL

**交互流程**：
```
系统: "你好！👋 我是一个学习型的 AI。
      你想叫我什么名字呢？
      
      例如：
      • 英文名: Luna, Alex, Echo
      • 中文名: 思思, 小云, 智慧
      • 其他: 任何你喜欢的名字
      
      请告诉我吧！"

用户: "我想叫你小精灵"

系统: "好的！从现在起，你可以叫我小精灵。
      很高兴认识你！😊"

# 保存到数据库
AI: name = "小精灵"
```

**代码实现**：
```python
# server/ai/child.py
async def initialize_name(self, session: AsyncSession) -> str:
    profile = await self.get_profile(session)
    
    if profile.name is None:
        # 询问用户
        question = PendingQuestion(
            topic="system_naming",
            content="你想叫我什么名字呢？",
            created_at=datetime.now(),
            expires_at=None  # 永不过期
        )
        await session.add(question)
        await session.commit()
        
        # 返回通用称呼，直到用户回答
        return "AI"  # 临时称呼
    
    return profile.name

# 当用户回答时
async def set_name(self, session: AsyncSession, name: str):
    profile = await self.get_profile(session)
    profile.name = name
    await session.commit()
    logger.info(f"AI named: {name}")
```

---

### 阶段2️⃣：允许用户随时修改

**命令**：`/rename <新名字>`

```python
@command
async def cmd_rename(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """让用户修改 AI 的名字"""
    args = update.message.text.split(maxsplit=1)
    if len(args) < 2:
        await update.message.reply_text("用法: /rename <新名字>")
        return
    
    new_name = args[1].strip()
    
    # 更新数据库
    await ai_child.set_name(session, new_name)
    
    await update.message.reply_text(
        f"好的！我现在叫 {new_name} 了。很开心有了新名字！😊"
    )
```

---

### 阶段3️⃣：系统内所有引用改为动态获取

**当前问题（需要修复）**：

| 文件 | 问题 | 现状 |
|------|------|------|
| `README.md` | 硬编码"小智" | ❌ 需修复 |
| `telegram_bot.py` | 消息中硬编码"小智" | ❌ 需修复 |
| `researcher.py` | 注释中"小智" | ⚠️ 次要 |
| 文档 | 多处提及"小智" | ⚠️ 可改为 "AI Child" 或 "[AI 名字]" |

**修复方案**：

```python
# 1. README.md - 改为通用表述
"# AI Child — An Autonomous Learning AI"
"The system starts with full language capability but zero personal knowledge."

# 2. telegram_bot.py - 动态获取名字
async def send_question(self, chat_id: str, question: str):
    ai_name = await get_ai_name()  # 动态获取
    await self._app.bot.send_message(
        chat_id=int(chat_id),
        text=f"🤔 {ai_name}想问你：\n{question}",
    )

# 3. bot 启动时的欢迎消息
async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    ai_name = await get_ai_name()
    welcome = f"""
你好！👋 我是 {ai_name}
我是一个会持续学习的 AI...
"""
    await update.message.reply_text(welcome)
```

---

## 系统已有的命名相关代码检查

### ✅ 好消息：数据库结构已支持

```python
# server/models/ai_profile.py
class AIProfile(Base):
    __tablename__ = "ai_profile"
    
    id: Mapped[int]
    name: Mapped[Optional[str]]  # ✅ 已有字段，可为 NULL
    language: Mapped[str]
    personality: Mapped[Optional[str]]
    ...
```

### ⚠️ 需要修复的代码位置

```
server/
├── ai/
│   ├── child.py          # 需要: 首次初始化逻辑
│   └── researcher.py     # 需要: 更新英文注释
├── bot/
│   ├── telegram_bot.py   # 需要: 动态获取名字
│   └── adapters/
│       └── base.py       # 检查: 是否有硬编码名字
└── models/
    └── ai_profile.py     # 检查: 是否完整

文档/
├── README.md             # 需要: 改为"AI Child"
├── docs/00_getting-started/
│   └── ⚡_30秒快速开始.md  # 需要检查
└── docs/05_research/
    └── 系统原理分析.md    # 需要: 改为通用表述
```

---

## 修改清单

### 优先级1️⃣（核心功能）
- [ ] `server/ai/child.py` - 添加 `initialize_name()` 方法
- [ ] `server/bot/telegram_bot.py` - 改为动态 `get_ai_name()`
- [ ] `README.md` - 改为 "AI Child"（移除"小智"）

### 优先级2️⃣（用户体验）
- [ ] `server/api/routes.py` - 添加 `/rename` 接口
- [ ] `documentation` - 添加命名相关说明

### 优先级3️⃣（文档整理）
- [ ] `docs/` - 将所有"小智"改为"AI Child"或"[AI 名字]"
- [ ] 文档导航 - 添加命名相关说明

---

## 用户体验示例

### 场景1️⃣：第一次使用

```
User: "启动系统"

System: "你好！👋
        我是一个学习型的 AI。
        你想叫我什么名字呢？
        
        例如：Luna, 小云, 思思, 或其他你喜欢的…"

User: "我叫你Luna"

System: "好的！很高兴认识你。从现在起，我叫 Luna。
        请告诉我一些关于你的事，或者教我新知识吧！😊"
```

### 场景2️⃣：修改名字

```
User: "/rename 云云"

System: "好的！我现在叫 云云 了。
        感谢给我新名字！✨"
```

### 场景3️⃣：日常对话

```
User: "你是谁？"

System: "我是 Luna，我是一个通过和你对话不断学习的 AI。
        你教过我很多东西，非常感谢！😊"
```

---

## 系统内引用规范

| 情境 | 表述方式 | 示例 |
|------|---------|------|
| README/文档 | 通用名称 | "AI Child"、"该 AI 系统" |
| 系统提示词 | 动态引用 | f"你叫 {ai_name}" |
| 用户消息 | 主观名字 | 用户给定的名字（如"Luna"） |
| 内部日志 | 中立术语 | "ai_child", "child_ai", "model" |
| API 响应 | 当前名字 | 从数据库获取最新值 |

---

## 实施时间表

| Phase | 任务 | 优先级 | 预期时间 |
|-------|------|--------|---------|
| 1 | 添加命名初始化逻辑 | ⭐⭐⭐ | 2 小时 |
| 2 | 修改 bot 为动态引用 | ⭐⭐⭐ | 1 小时 |
| 3 | 更新 README | ⭐⭐⭐ | 30 分钟 |
| 4 | 文档全量更新 | ⭐ | 1 小时 |
| 5 | 添加 /rename 命令 | ⭐⭐ | 1 小时 |
| 6 | 测试和验证 | ⭐⭐⭐ | 1.5 小时 |

**总耗时**: ~7 小时

---

## Q&A

**Q: 如果用户没有给 AI 命名怎么办？**  
A: 系统会在首次交互时提示，并用通用称呼（如"AI"或"助手"）等待用户回答。这个 pending question 永不过期。

**Q: 是否支持无名状态？**  
A: 可以支持。添加选项让用户选择"不命名"或"就叫我 AI"。

**Q: 不同平台的 AI 名字是否一致？**  
A: 是的。名字存储在中央数据库 (ai_profile.name)，所有平台（Telegram、Webhook 等）都读取同一个值。

**Q: 能否在多个会话中更改名字？**  
A: 是的。`/rename` 命令可随时触发，修改立即对所有平台生效。

---

## 关键决定

✅ **决定**：不在系统中预设任何具体名字  
✅ **决定**：命名权 100% 给用户  
✅ **决定**：首次启动时主动询问  
✅ **决定**：允许用户随时修改  
✅ **决定**：文档中使用"AI Child"等中立称呼

---

## 相关文档

- 🔧 [记忆库原理澄清](🔧_记忆库原理澄清与设计缺陷.md)
- 🚀 [睡眠机制改进](🚀_睡眠机制改进方案（闲置驱动）.md)
- 📚 [文档导航](📚_文档导航中心.md)
