# AI Child 人格保存系统深度研究报告

**报告日期**：2026-03-21  
**研究范围**：人格存储、恢复、导出导入、API端点  
**研究关键词**：profile, personality, state, persistence, export, import, backup

---

## 📋 执行摘要

AI Child 项目已实现了**基础的人格保存机制**，主要通过 SQLite 数据库的 `AIProfile` 单例表存储 AI 的身份信息。然而，**缺乏导出/导入功能和用户友好的备份机制**。

### 🔍 核心发现

| 项目 | 状态 | 评分 |
|------|------|------|
| 数据库架构 | ✅ 完整 | 4/5 |
| 人格存储逻辑 | ✅ 完整 | 4/5 |
| API 端点 | ⚠️ 基础 | 2/5 |
| 导出导入功能 | ❌ 缺失 | 0/5 |
| 备份恢复机制 | ❌ 缺失 | 0/5 |

---

## 1️⃣ 数据库表结构详解

### 1.1 核心表：AIProfile（人格表）

**表定义位置**：[server/models/__init__.py#L94-L109](server/models/__init__.py#L94-L109)

```python
class AIProfile(Base):
    """
    Singleton row (id=1) holding the AI child's personal profile.
    The AI starts unnamed. Its very first proactive question asks 
    the user what to call it.
    """
    __tablename__ = "ai_profile"

    id = Column(Integer, primary_key=True, default=1)              # 固定为1
    name = Column(String(128), nullable=True)                      # AI名字（初始NULL）
    created_at = Column(DateTime(timezone=True), default=_utcnow)  # 创建时间
    named_at = Column(DateTime(timezone=True), nullable=True)      # 命名时间
    
    # Sleep state
    is_sleeping = Column(Boolean, default=False)                   # 睡眠状态标志
    last_consolidation_summary = Column(Text, nullable=True)       # 睡眠记忆摘要
```

**设计特点**：
- ✅ **单例模式**：`id=1` 保证全局唯一
- ✅ **逐步初始化**：`name=NULL` → 用户命名 → `name="小明"`
- ✅ **时间戳追踪**：记录创建和命名时间
- ⚠️ **字段有限**：仅包含最小必要字段，缺乏扩展性

### 1.2 相关表：AI 状态/配置表

| 表名 | 主要字段 | 用途 | 文件位置 |
|------|--------|------|--------|
| **conversations** | role, content, timestamp, media_path | 对话历史 | [models/__init__.py#L28-L40](server/models/__init__.py#L28-L40) |
| **knowledge** | topic, content, source, confidence | 显式知识 | [models/__init__.py#L43-L53](server/models/__init__.py#L43-L53) |
| **pending_questions** | question, topic, answered, answer | 待答问题 | [models/__init__.py#L56-L67](server/models/__init__.py#L56-L67) |
| **tools** | name, description, code, parameters_schema | 自创工具 | [models/__init__.py#L70-L82](server/models/__init__.py#L70-L82) |
| **sleep_events** | event_type, message, consumed | 睡眠事件 | [models/__init__.py#L112-L124](server/models/__init__.py#L112-L124) |

---

## 2️⃣ 人格存储和恢复逻辑

### 2.1 核心函数库

**模块**：[server/ai/profile.py](server/ai/profile.py)（180行）

#### 函数 1：获取或创建人格 

```python
async def get_or_create_profile(session: AsyncSession) -> AIProfile:
    """Return the singleton profile row, creating it if this is the first run."""
    result = await session.execute(select(AIProfile).where(AIProfile.id == 1))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = AIProfile(id=1, name=None)
        session.add(profile)
        await session.commit()
    return profile
```

**特点**：
- ✅ 幂等性：多次调用返回相同对象
- ✅ 自动初始化：首次创建时自动生成单例
- **使用场景**：所有需要访问人格信息的地方

#### 函数 2：获取 AI 名字

```python
async def get_ai_name(session: AsyncSession) -> Optional[str]:
    """Return the AI's name, or None if it has not been named yet."""
    profile = await get_or_create_profile(session)
    return profile.name
```

#### 函数 3：保存 AI 名字

```python
async def set_ai_name(session: AsyncSession, name: str) -> None:
    """Persist the AI's name in its profile."""
    profile = await get_or_create_profile(session)
    profile.name = name
    profile.named_at = datetime.now(timezone.utc)  # 记录命名时刻
    await session.commit()
    logger.info("AI child has been named: '%s'", name)
```

**特点**：
- ✅ 同步更新两个字段：`name` 和 `named_at`
- ✅ 包含日志记录便于审计
- **约束**：一旦设置无法修改（缺乏重命名功能）

#### 函数 4：从自由文本提取名字

```python
async def extract_name_from_answer(answer: str) -> str:
    """
    Use GPT-4o to extract a proper name from a free-form user reply.
    
    Examples:
      "就叫小明吧"  → "小明"
      "你叫 Alex"  → "Alex"
      "Tom"        → "Tom"
    """
    prompt = (
        f"Someone was asked what to name a newly born AI child. They replied:\n"
        f'"{answer}"\n\n'
        f"Extract the name they chose. Return ONLY the name — no explanation, "
        f"no punctuation around it."
    )
    response = await _client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=32,
        temperature=0.1,
    )
    extracted = (response.choices[0].message.content or "").strip()
    if extracted and len(extracted) <= 64:
        return extracted
    return answer.strip()[:64]  # Fallback
```

**特点**：
- ✅ 使用 GPT-4o 理解自然语义
- ✅ 降温度（temperature=0.1）确保准确性
- ✅ 提供降级方案（超长或解析失败时截断）

#### 函数 5：初始化命名问卷

```python
async def ensure_name_question_exists(session: AsyncSession) -> None:
    """
    If the AI has no name yet, ensure there is exactly one pending
    name-seeking question in the DB.
    
    Called once at server startup so the Telegram bot's question poller
    will immediately push it to connected chats.
    """
    name = await get_ai_name(session)
    if name is not None:
        return  # Already named — nothing to do

    result = await session.execute(
        select(PendingQuestion)
        .where(PendingQuestion.topic == NAME_QUESTION_TOPIC)
        .where(PendingQuestion.answered == False)
    )
    if result.scalar_one_or_none() is None:
        session.add(
            PendingQuestion(
                question=NAME_QUESTION_TEXT,
                topic=NAME_QUESTION_TOPIC,  # "__name__"
            )
        )
        await session.commit()
```

**特点**：
- ✅ 服务器启动时调用
- ✅ 确保名字问题仅出现一次
- **关键标记**：`topic = "__name__"` 用于特殊处理

### 2.2 完整命名流程

```
服务器启动
    ↓
[server/main.py#43] await initialize_sleep_state()
    ↓
[profile.py] ensure_name_question_exists()
    ↓
检查：AI已命名？
    ├─ YES → 无操作，返回
    └─ NO → 创建 PendingQuestion(topic="__name__")
    ↓
用户通过Telegram/API回答
    ↓
[server/api/teach.py#78] POST /teach/questions/{id}/answer
    ↓
answer_question(session, question_id, answer)
    ↓
检查：topic == "__name__"?
    ├─ YES → 特殊处理
    │         ├─ extract_name_from_answer(answer)
    │         ├─ set_ai_name(session, name)
    │         └─ 返回温暖的确认消息
    │
    └─ NO → 正常处理，存储为知识
```

---

## 3️⃣ API 端点与接口

### 3.1 已实现端点

#### 端点 1：获取人格信息

```http
GET /profile
```

**代码**：[server/main.py#91-96](server/main.py#L91-L96)

```python
@app.get("/profile", tags=["profile"])
async def get_profile(session: AsyncSession = Depends(get_session)):
    """Return the AI child's current profile (name, whether it has been named)."""
    name = await get_ai_name(session)
    return {"name": name, "has_name": name is not None}
```

**响应示例**：

```json
{
  "name": "小明",
  "has_name": true
}
```

或（命名前）：

```json
{
  "name": null,
  "has_name": false
}
```

#### 端点 2：回答命名问题

```http
POST /teach/questions/{question_id}/answer
Content-Type: application/json

{"answer": "就叫小明吧"}
```

**代码**：[server/api/teach.py#78-107](server/api/teach.py#L78-L107)

**特殊逻辑**：
- 检测 `question.topic == "__name__"`
- 调用 `extract_name_from_answer()` 提取名字
- 调用 `set_ai_name()` 永久保存
- 返回确认消息

**响应示例**：

```json
{
  "reply": "太好了！以后我就叫小明了！谢谢你给我起了这么好听的名字！😊"
}
```

### 3.2 缺失的端点（建议实现）

| 端点 | 方法 | 用途 | 优先级 |
|------|------|------|--------|
| `/profile/export` | GET | 导出完整人格数据 | 🔴 高 |
| `/profile/import` | POST | 导入人格备份 | 🔴 高 |
| `/profile/backup` | POST | 创建备份 | 🟡 中 |
| `/profile/restore` | POST | 恢复备份 | 🟡 中 |
| `/profile/history` | GET | 人格演变历史 | 🟢 低 |
| `/profile/rename` | PATCH | 重命名 AI | 🟢 低 |

---

## 4️⃣ 睡眠周期中的状态变化

### 4.1 架构概览

**文件**：[server/ai/sleep.py](server/ai/sleep.py)（约200行）

```
AIProfile 字段变化时间表
├─ 创建时
│  ├─ created_at = now
│  ├─ name = NULL
│  └─ is_sleeping = False
│
├─ 用户命名时
│  ├─ name = "小明"
│  └─ named_at = now
│
├─ 每天 22:00（睡眠时）
│  ├─ is_sleeping = True
│  ├─ last_consolidation_summary = "今天学到..." (后台更新)
│  └─ 创建 SleepEvent(type="sleep")
│
└─ 每天 07:00（唤醒时）
   ├─ is_sleeping = False
   └─ 创建 SleepEvent(type="wake")
```

### 4.2 睡眠时的记忆巩固

**函数**：`consolidate_memories()`

```python
async def consolidate_memories(session: AsyncSession, name: str | None):
    """
    At bedtime, review today's conversations and generate insights.
    """
    # 1. 查询今日所有知识项
    items = await session.execute(
        select(KnowledgeItem).where(
            KnowledgeItem.timestamp >= today_start
        )
    )
    
    # 2. 使用 GPT-4o 生成洞察
    summary = await _client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "user",
                "content": f"Consolidate these learnings: {topics}"
            }
        ]
    )
    
    # 3. 保存摘要到 AIProfile
    profile = await get_or_create_profile(session)
    profile.last_consolidation_summary = summary_content
    await session.commit()
```

**作用**：
- ✅ 加强知识记忆
- ✅ 生成新的好奇心问题
- ✅ 为早晨问候提供上下文

---

## 5️⃣ 导出导入功能设计方案

### 5.1 导出 API 设计

**建议实现**：

```python
@app.get("/profile/export")
async def export_profile(session: AsyncSession = Depends(get_session)):
    """Export complete AI personality snapshot as JSON."""
    profile = await get_or_create_profile(session)
    
    # 1. 获取所有相关数据
    conversations = await get_recent_messages(session, limit=None)
    knowledge = await get_all_knowledge(session)
    questions = await get_unanswered_questions(session)
    tools = await get_all_tools(session)
    
    # 2. 构造导出对象
    export_data = {
        "profile": {
            "name": profile.name,
            "created_at": profile.created_at.isoformat(),
            "named_at": profile.named_at.isoformat() if profile.named_at else None,
            "is_sleeping": profile.is_sleeping,
            "last_consolidation_summary": profile.last_consolidation_summary
        },
        "statistics": {
            "total_conversations": len(conversations),
            "total_knowledge_items": len(knowledge),
            "pending_questions": len(questions),
            "tools_created": len(tools)
        },
        "metadata": {
            "export_version": "1.0",
            "app_version": "Phase1",
            "export_at": datetime.now(timezone.utc).isoformat(),
            "backup_format": "full"  # 可选: "full" | "profile_only" | "metadata"
        }
    }
    
    return export_data
```

**响应示例**：

```json
{
  "profile": {
    "name": "小明",
    "created_at": "2026-03-01T10:00:00+00:00",
    "named_at": "2026-03-01T10:05:30+00:00",
    "is_sleeping": false,
    "last_consolidation_summary": "今天学到了..."
  },
  "statistics": {
    "total_conversations": 156,
    "total_knowledge_items": 42,
    "pending_questions": 7,
    "tools_created": 3
  },
  "metadata": {
    "export_version": "1.0",
    "app_version": "Phase1",
    "export_at": "2026-03-21T12:00:00+00:00",
    "backup_format": "full"
  }
}
```

### 5.2 导入 API 设计

```python
@app.post("/profile/import")
async def import_profile(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session)
):
    """Import personality from exported JSON backup."""
    try:
        content = await file.read()
        import_data = json.loads(content)
        
        # 1. 验证版本兼容性
        version = import_data.get("metadata", {}).get("export_version")
        if version != "1.0":
            raise ValueError(f"Unsupported backup version: {version}")
        
        # 2. 恢复 AIProfile
        profile = await get_or_create_profile(session)
        profile_data = import_data.get("profile", {})
        if profile_data.get("name"):
            profile.name = profile_data["name"]
            profile.named_at = parse(profile_data["named_at"]) if profile_data.get("named_at") else None
        
        await session.commit()
        
        return {
            "status": "success",
            "profile_restored": profile.name,
            "items_imported": import_data["statistics"]
        }
    
    except Exception as e:
        logger.error(f"Import failed: {e}")
        raise HTTPException(status_code=400, detail=f"Import failed: {str(e)}")
```

### 5.3 备份文件格式建议

```json
{
  "format": "ai-child-backup",
  "version": "1.0",
  "created_at": "2026-03-21T12:00:00+00:00",
  
  "profile": {
    "name": "小明",
    "created_at": "2026-03-01T10:00:00+00:00",
    "named_at": "2026-03-01T10:05:30+00:00",
    "is_sleeping": false,
    "last_consolidation_summary": "记忆总结..."
  },
  
  "data": {
    "conversations": [
      {
        "id": 1,
        "role": "user",
        "content": "你叫什么名字？",
        "timestamp": "2026-03-01T10:00:30+00:00"
      }
    ],
    "knowledge": [
      {
        "id": 1,
        "topic": "Python",
        "content": "Python是一门编程语言",
        "source": "user",
        "confidence": 100
      }
    ],
    "tools": [
      {
        "id": 1,
        "name": "calculate_factorial",
        "description": "计算阶乘",
        "code": "def factorial(n): ..."
      }
    ]
  },
  
  "metadata": {
    "backup_type": "full",
    "database_size_mb": 2.5,
    "export_tool_version": "1.0"
  }
}
```

---

## 6️⃣ 数据持久化架构总体视图

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Child 数据持久化层                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          SQLite 数据库 (ai_child.db)                   │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │                                                       │  │
│  │  AIProfile (单例)                                     │  │
│  │  ├─ id=1                                             │  │
│  │  ├─ name: "小明" (NULL→命名→固定)                    │  │
│  │  ├─ is_sleeping: true/false (22h→7h变化)           │  │
│  │  └─ last_consolidation_summary: "今天学到..."       │  │
│  │                                                       │  │
│  │  Conversations (对话历史)                            │  │
│  │  ├─ 用户输入                                         │  │
│  │  ├─ AI 回复                                          │  │
│  │  └─ 多媒体附件 (images, audio)                       │  │
│  │                                                       │  │
│  │  Knowledge (知识库)                                  │  │
│  │  ├─ 显式教学内容                                     │  │
│  │  ├─ 自主研究结果                                     │  │
│  │  └─ 置信度评分 (0-100)                              │  │
│  │                                                       │  │
│  │  PendingQuestions (好奇心)                           │  │
│  │  ├─ 用户提问                                         │  │
│  │  ├─ 待答问卷                                         │  │
│  │  └─ 特殊: "__name__" 主题                           │  │
│  │                                                       │  │
│  │  Tools (自创工具)                                    │  │
│  │  ├─ Python 代码                                      │  │
│  │  └─ OpenAI 函数签名                                  │  │
│  │                                                       │  │
│  │  SleepEvents (睡眠日志)                              │  │
│  │  ├─ 睡眠事件                                         │  │
│  │  ├─ 唤醒事件                                         │  │
│  │  └─ 个性化消息                                       │  │
│  │                                                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                           ↑↓                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              API 层 (FastAPI)                         │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │                                                       │  │
│  │  GET  /profile            - 读取人格                 │  │
│  │  POST /teach/questions/*/answer  - 回答并保存        │  │
│  │  GET  /teach/knowledge    - 查看学习积累             │  │
│  │  POST /teach/...          - 教学新知识               │  │
│  │  GET  /profile/export     - 导出备份 ⭐ (建议)      │  │
│  │  POST /profile/import     - 导入备份 ⭐ (建议)      │  │
│  │                                                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                           ↑↓                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │            业务逻辑层 (server/ai/)                   │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │                                                       │  │
│  │  profile.py    ← AIProfile 操作                       │  │
│  │  sleep.py      ← 睡眠周期管理，记忆巩固            │  │
│  │  memory.py     ← 对话/知识 CRUD                      │  │
│  │  child.py      ← 主要对话逻辑                        │  │
│  │  researcher.py ← 自主研究                            │  │
│  │  tools.py      ← 工具管理和执行                      │  │
│  │                                                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                           ↑↓                                 │
│  ┌──────────────────────────────────────────────────────┐  │
│  │          外部系统 (Bots, 客户端)                     │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │                                                       │  │
│  │  Telegram Bot  ← 推送消息                            │  │
│  │  WebSocket     ← 实时通信                            │  │
│  │  REST Client   ← 调用 API                            │  │
│  │                                                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 7️⃣ 现状对标与改进建议

### 7.1 功能对标

| 功能 | 实现状态 | 完整度 | 备注 |
|------|--------|--------|------|
| 人格创建 | ✅ 完整 | 100% | 单例自动初始化 |
| 命名流程 | ✅ 完整 | 100% | GPT-4o自然语言理解 |
| 状态查询 | ✅ 完整 | 100% | GET /profile |
| 睡眠周期 | ✅ 完整 | 100% | 24小时自动切换 |
| **导出备份** | ❌ 缺失 | 0% | 需要实现 |
| **导入恢复** | ❌ 缺失 | 0% | 需要实现 |
| **版本控制** | ❌ 缺失 | 0% | 需要实现 |
| **跨设备同步** | ❌ 缺失 | 0% | 需要实现 |
| 数据加密 | ❌ 缺失 | 0% | 建议增加 |

### 7.2 数据库改进建议

**扩展 AIProfile 表**：

```sql
ALTER TABLE ai_profile ADD COLUMN (
  -- 个性化配置
  preferred_language VARCHAR(16) DEFAULT 'zh-CN',
  personality_traits TEXT,
  mood_score INTEGER DEFAULT 50,
  
  -- 隐私和备份
  privacy_level VARCHAR(32) DEFAULT 'private',
  last_backup_at DATETIME,
  backup_version INTEGER DEFAULT 0,
  
  -- 开发调试
  debug_mode BOOLEAN DEFAULT FALSE,
  creation_method VARCHAR(32)  -- "ui" | "import" | "api"
);
```

### 7.3 开发路线图（按优先级）

#### Phase 1（立即）
- [ ] 实现 `GET /profile/export` 端点
- [ ] 实现 `POST /profile/import` 端点
- [ ] 确定导出数据格式标准
- [ ] 编写导入/导出测试用例

#### Phase 2（1-2周）
- [ ] 添加备份历史追踪（`last_backup_at`, `backup_version`）
- [ ] 实现增量备份（仅导出变化的数据）
- [ ] 添加备份数据验证机制
- [ ] 实现导出数据加密

#### Phase 3（1个月）
- [ ] 多用户隔离（添加 `user_id` 字段）
- [ ] 云备份集成（AWS S3 / 阿里云）
- [ ] 备份版本控制和恢复选择器
- [ ] Web UI 备份管理界面

#### Phase 4（2-3个月）
- [ ] 跨设备同步
- [ ] 个性化参数持久化
- [ ] 迁移工具（旧版本升级）

---

## 8️⃣ 代码示例和最佳实践

### 8.1 如何安全地重置人格

**推荐方式**（而非直接删除）：

```python
async def reset_profile(session: AsyncSession):
    """创建一个全新人格，保留历史数据。"""
    # 1. 保存旧人格快照（备份）
    old_profile = await get_or_create_profile(session)
    backup = {
        "old_name": old_profile.name,
        "reset_at": datetime.now(timezone.utc).isoformat(),
        "reset_reason": "User requested reset"
    }
    
    # 2. 生成新人格
    profile = await get_or_create_profile(session)
    profile.name = None
    profile.named_at = None
    profile.is_sleeping = False
    profile.last_consolidation_summary = None
    await session.commit()
    
    # 3. 重新创建命名问题
    await ensure_name_question_exists(session)
    
    return backup
```

### 8.2 如何迁移人格到新系统

```python
async def migrate_profile(
    old_export_file: str,
    session: AsyncSession
):
    """从导出文件恢复人格到新系统。"""
    with open(old_export_file, 'r') as f:
        data = json.load(f)
    
    # 1. 验证备份完整性
    required_fields = {"profile", "metadata"}
    if not required_fields.issubset(data.keys()):
        raise ValueError("Corrupted backup file")
    
    # 2. 检查版本兼容性
    version = data["metadata"]["export_version"]
    if not is_compatible_version(version):
        raise ValueError(f"Version {version} not supported")
    
    # 3. 恢复数据
    profile = await get_or_create_profile(session)
    profile.name = data["profile"]["name"]
    profile.named_at = parse_datetime(data["profile"]["named_at"])
    await session.commit()
    
    return {"status": "migrated", "name": profile.name}
```

---

## 9️⃣ 常见问题解答 (FAQ)

### Q1: 为什么AI名字一旦设置就无法修改?

**A**: 这是设计选择，用于维护 AI 身份的一致性。在现实中，改名字是重大事件。如果需要支持重命名，可以：
1. 添加新的 `rename_history` 表
2. 记录所有名字变更和时间戳
3. 在系统提示中提及过去的名字

### Q2: 睡眠状态中的 `last_consolidation_summary` 什么时候更新?

**A**: 在每天 22:00（睡眠时）由后台任务 `consolidate_memories()` 自动更新。该摘要：
- 总结当天学到的知识
- 生成明天的好奇心问题
- 用于 07:00 早晨问候

### Q3: 如何确保导入备份时数据不重复?

**A**: 建议采用策略：
1. **合并策略**：新导入的数据和现有数据合并，去重
2. **覆盖策略**：完全替换（需要备份原有数据）
3. **选择策略**：用户选择导入哪些表

### Q4: 可以同时运行多个AI实例吗?

**A**: 当前设计：**不可以** (通过 `id=1` 强制单例)。如果需要多AI支持：
1. 改为 `id = user_id` 或 `id = UUID`
2. 扩展 SQLite 为分布式数据库（PostgreSQL）
3. 实现用户隔离逻辑

### Q5: 备份文件是否包含敏感信息?

**A**: 是的。当前备份包含：
- 所有对话历史（可能包含隐私内容）
- API 调用日志
- **建议**：
  - 实现导出前的数据混淆
  - 添加加密选项 (`--encrypt`)
  - 记录备份访问审计日志

---

## 🔟 总结与建议

### 核心发现

✅ **已完成**：
- 稳固的单例模式 AIProfile 表
- 自然语言名字提取（GPT-4o）
- 24 小时睡眠周期管理
- 记忆巩固机制

❌ **缺失**：
- 导出/导入功能
- 数据备份恢复
- 多用户隔离
- 云同步能力

### 优先级建议

🔴 **立即（本周）**：实现 `/profile/export` 和 `/profile/import` 端点

🟡 **短期（1-2周）**：
- 完整数据备份格式
- 备份验证和恢复测试

🟢 **中期（1-3个月）**：
- 云备份集成
- 跨设备同步
- 多用户支持

### 参考资源

- [AI Child 架构流程图详解](架构流程图详解.md)
- [防幻觉工具实现报告](防幻觉工具实现报告.md)
- [系统原理分析](系统原理分析.md)

---

**报告完成日期**：2026-03-21  
**下次更新预计**：待导出导入功能实现后
