# AI Child 项目 - 记忆遗忘机制深度分析报告

**生成日期**: 2026-03-21  
**分析范围**: 记忆持久化、自动删除、过期策略、睡眠巩固、缓存失效、内存管理  
**关键文件**: `server/ai/memory.py`, `server/ai/sleep.py`, `server/models/__init__.py`, `server/ai/tools.py`

---

## 📊 执行摘要

| 方面 | 现状 | 评分 |
|------|------|------|
| 📦 记忆持久化 | ✅ 完整（SQLite） | 5/5 |
| 🗑️ 自动删除机制 | ❌ 缺失 | 0/5 |
| ⏳ 记忆过期策略 | ⚠️ 部分（仅缓存） | 2/5 |
| 💤 睡眠巩固机制 | ✅ 完整 | 4/5 |
| 🔄 缓存失效策略 | ✅ 基础 | 3/5 |
| 🧠 内存管理 | ⚠️ 被动 | 2/5 |

---

## 1️⃣ 记忆持久化（数据库表设计）

### 数据库架构

**文件**: [`server/models/__init__.py`](server/models/__init__.py)  
**ORM**: SQLAlchemy + AsyncIO  
**数据库**: SQLite (默认 `./ai_child.db`)

### 数据表设计

#### 📋 conversations（对话历史表）
```python
class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    role = Column(String(16))              # "user" | "assistant"
    content = Column(Text)                 # 对话内容
    content_type = Column(String(32))      # "text" | "image" | "audio" | "mixed"
    media_path = Column(String(512))       # 媒体文件路径
    timestamp = Column(DateTime(tz=True))  # 记录时间戳 (UTC)
    metadata_ = Column(JSON)               # 附加元数据
```
**特性**:
- ✅ 完整的对话历史记录
- ✅ 支持多媒体内容
- ✅ 时间戳索引（可追踪对话)
- ❌ **无自动过期机制**

#### 📚 knowledge（知识库表）
```python
class KnowledgeItem(Base):
    __tablename__ = "knowledge"
    
    id = Column(Integer, primary_key=True)
    topic = Column(String(256), index=True)     # 主题 (索引)
    content = Column(Text)                      # 知识内容
    source = Column(String(64))                 # "user" | "consolidation" | "web_search"
    confidence = Column(Integer)                # 0-100 置信度
    timestamp = Column(DateTime(tz=True))       # 创建时间
    last_reviewed = Column(DateTime(tz=True))   # 最后复习时间
```
**特性**:
- ✅ 知识分类和追踪
- ✅ 置信度评分机制
- ✅ 来源标记（用于溯源）
- ⚠️ `last_reviewed` 字段虽已定义但未被充分利用

#### ❓ pending_questions（待答问题表）
```python
class PendingQuestion(Base):
    __tablename__ = "pending_questions"
    
    id = Column(Integer, primary_key=True)
    question = Column(Text)               # 问题内容
    topic = Column(String(256))           # 主题分类
    answered = Column(Boolean, default=False)     # 是否已回答
    answer = Column(Text, nullable=True)  # 答案内容
    created_at = Column(DateTime(tz=True))        # 创建时间
    answered_at = Column(DateTime(tz=True))       # 回答时间
```
**特性**:
- ✅ 好奇心驱动的学习追踪
- ✅ 问题生命周期管理
- ❌ **无自动删除已回答问题的机制**

#### 🤖 ai_profile（人格档案表）- **单例表**
```python
class AIProfile(Base):
    __tablename__ = "ai_profile"
    
    id = Column(Integer, primary_key=True, default=1)  # 强制单例
    name = Column(String(128))                         # AI名字
    created_at = Column(DateTime(tz=True))             # 创建时间
    named_at = Column(DateTime(tz=True))               # 命名时间
    is_sleeping = Column(Boolean, default=False)       # 睡眠状态
    last_consolidation_summary = Column(Text)          # 最近睡眠整理摘要
```
**特性**:
- ✅ 身份持久化
- ✅ 睡眠状态管理
- ✅ 记忆巩固摘要缓存

#### 💤 sleep_events（睡眠事件表）
```python
class SleepEvent(Base):
    __tablename__ = "sleep_events"
    
    id = Column(Integer, primary_key=True)
    event_type = Column(String(16))        # "sleep" | "wake"
    message = Column(Text)                 # 个性化的睡眠/唤醒消息
    consumed = Column(Boolean, default=False)  # 是否已被消费
    created_at = Column(DateTime(tz=True))     # 创建时间
```
**特性**:
- ✅ 睡眠周期事件跟踪
- ✅ 事件消费模式（防重复）
- ❌ **无消费历史清理机制**

#### 🛠️ tools（工具表）
```python
class Tool(Base):
    __tablename__ = "tools"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, index=True)
    description = Column(Text)
    code = Column(Text)                    # Python源代码
    parameters_schema = Column(JSON)       # OpenAI函数调用规范
    call_count = Column(Integer, default=0)  # 调用统计
    created_at = Column(DateTime(tz=True))
```
**特性**:
- ✅ 动态工具创建和存储
- ✅ 使用频率追踪
- ❌ **无工具删除或弃用机制**

---

## 2️⃣ 自动删除/遗忘机制

### 现状分析

**❌ 核心发现：系统完全缺乏主动遗忘机制**

### 代码证据

#### 内存管理函数（`server/ai/memory.py`）
```python
async def add_message(session, role, content, ...):
    """添加消息 - 永久持久化"""
    msg = Conversation(role=role, content=content, ...)
    session.add(msg)
    await session.commit()
    # ❌ 无过期检查，无自动删除

async def get_recent_messages(session, limit: int = 20):
    """获取最近的消息 - 软限制"""
    result = await session.execute(
        select(Conversation)
        .order_by(Conversation.timestamp.desc())
        .limit(limit)  # ⚠️ 只在查询时限制，不删除旧消息
    )
    return list(reversed(rows))

async def add_knowledge(session, topic, content, source="user", confidence=100):
    """添加知识项 - 无过期"""
    item = KnowledgeItem(topic=topic, content=content, source=source, confidence=confidence)
    session.add(item)
    await session.commit()
    # ❌ 无时间限制，无置信度衰减
```

### 数据增长风险

```python
# 问题：随着时间推移，数据表无限增长
- conversations: 每次对话 +1，无删除 → ∞ 行
- knowledge: 消息越多，知识越多 → ∞ 增长
- pending_questions: 已回答问题不删除 → 堆积
- sleep_events: 每晚1-2个事件，已消费不清理 → ∞ 堆积
```

---

## 3️⃣ 记忆过期策略

### 策略级别

| 级别 | 实现方式 | TTL/保留期 | 状态 |
|------|---------|-----------|------|
| **1. 上下文窗口** | `memory_context_turns` | 20轮 | ✅ |
| **2. 查询缓存** | `_knowledge_cache` | 5分钟 | ✅ |
| **3. 数据库保留** | 无 | ∞ | ❌ |
| **4. 自动衰减** | 无 | 无 | ❌ |

### 3.1 上下文窗口限制

**文件**: [`server/config.py`](server/config.py)  
**配置参数**:
```python
class Settings(BaseSettings):
    # 每次对话的历史上下文轮数
    memory_context_turns: int = 20
    
    # AI主动提问间隔
    proactive_question_interval: int = 2
```

**使用场景** (`server/ai/child.py`):
```python
history = await get_recent_messages(
    session, 
    limit=settings.memory_context_turns  # 限制为20条
)
```

**特性**:
- ✅ 防止上下文工作量过大
- ⚠️ 但**不删除历史数据**，只是查询限制
- ❌ 无配置时间衰减

### 3.2 查询缓存 TTL

**文件**: [`server/ai/tools.py`](server/ai/tools.py#L28-L29)  
**缓存定义**:
```python
# 全局内存缓存（应用级，非数据库）
_knowledge_cache: Dict[str, tuple] = {}      # (timestamp, data)
_confidence_cache: Dict[str, float] = {}     # 置信度缓存
```

**5分钟 TTL 实现** (`server/ai/tools.py:520-525`):
```python
cache_key = f"{topic}|{keywords}"
if cache_key in _knowledge_cache:
    cached_time, cached_data = _knowledge_cache[cache_key]
    import time
    if time.time() - cached_time < 300:  # 5分钟 = 300秒
        return json.dumps(cached_data)
    # ⚠️ 过期后，仍在字典中，等待GC清理
```

**缺陷分析**:
```
┌─ 问题 ──────────────────────────────────────────┐
│ 1. 缓存过期后KEY仍在内存中                        │
│ 2. 字典会无限增长（应该有清理机制）               │
│ 3. 应用重启时缓存丢失（无持久化）                 │
│ 4. 多进程下无法共享缓存                          │
└──────────────────────────────────────────────────┘
```

### 3.3 数据库保留策略

**当前**: ✅ 所有数据**永久保留**

**建议改进**:
```python
# 缺失的清理函数
async def cleanup_old_conversations(session, days: int = 90):
    """删除超过N天的对话"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    await session.execute(
        delete(Conversation).where(Conversation.timestamp < cutoff)
    )
    await session.commit()

async def cleanup_answered_questions(session):
    """删除已回答超过30天的问题"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    await session.execute(
        delete(PendingQuestion)
        .where(
            (PendingQuestion.answered == True) &
            (PendingQuestion.answered_at < cutoff)
        )
    )
    await session.commit()

async def cleanup_consumed_sleep_events(session, days: int = 7):
    """删除已消费超过N天的睡眠事件"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    await session.execute(
        delete(SleepEvent)
        .where(
            (SleepEvent.consumed == True) &
            (SleepEvent.created_at < cutoff)
        )
    )
    await session.commit()
```

---

## 4️⃣ 睡眠时的记忆巩固机制

### 架构概览

```
┌─ 睡眠周期 ───────────────────────────────────────────┐
│                                                     │
│  22:00 (睡眠时间)                                    │
│    ↓                                                │
│  [1] go_to_sleep()                                 │
│    • 标记 is_sleeping = True                        │
│    • 生成晚安消息                                   │
│    • 启动后台任务: consolidate_memories()           │
│    ↓                                                │
│  [2] consolidate_memories()                        │
│    • 查询最近 30 个知识项                            │
│    • 用 GPT-4o 分析、提取核心知识                   │
│    • 生成新的好奇心问题                             │
│    • 提高已复习知识的置信度                         │
│    ↓                                                │
│  [3] 存储巩固结果                                   │
│    • 新知识 → knowledge表 (source="consolidation") │
│    • 新问题 → pending_questions表                 │
│    • 摘要 → ai_profile.last_consolidation_summary  │
│    ↓                                                │
│  07:00 (唤醒时间)                                   │
│  [4] wake_up()                                      │
│    • 标记 is_sleeping = False                       │
│    • 生成早安消息（引用巩固内容）                   │
│    ↓                                                │
│  继续清醒状态...                                     │
└─────────────────────────────────────────────────────┘
```

### 核心代码

**文件**: [`server/ai/sleep.py`](server/ai/sleep.py#L150-L240)

#### 巩固函数完整实现

```python
async def consolidate_memories() -> str:
    """
    在睡眠时整理今天的学习。
    流程：
    1. 查询最近30个知识项
    2. 用GPT-4o分析并提取3个核心见解
    3. 生成2个新的好奇问题
    4. 提高已复习知识的置信度
    返回：巩固摘要字符串
    """
    logger.info("Memory consolidation starting …")
    summary = ""
    async with async_session() as session:
        try:
            # 第1步：查询最近30个知识项
            result = await session.execute(
                select(KnowledgeItem)
                .order_by(KnowledgeItem.timestamp.desc())
                .limit(30)
            )
            items = result.scalars().all()
            if not items:
                logger.info("Nothing to consolidate — no knowledge items found.")
                return ""

            # 第2步：格式化知识文本
            kb_text = "\n".join(
                f"- [{item.topic}] {item.content[:120]}"
                for item in items
            )
            name = await get_ai_name(session)
            name_str = name or "AI孩子"

            # 第3步：调用GPT-4o进行分析
            prompt = (
                f"你是{name_str}，正在睡眠中整理今天学到的知识。\n\n"
                f"已知内容：\n{kb_text}\n\n"
                f"请完成以下任务，严格以JSON格式返回，不要有任何额外文字：\n"
                f"1. 识别最重要的3个核心知识点，每个用一句话总结\n"
                f"2. 找出2个你仍然好奇或不确定的问题\n"
                f'{{"insights": ["...", "...", "..."], "questions": ["...", "..."]}}'
            )
            resp = await _client.chat.completions.create(
                model=settings.openai_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                temperature=0.3,  # 低温度 = 更稳定的分析
            )
            raw = (resp.choices[0].message.content or "").strip()

            # 第4步：解析JSON
            data: dict = {}
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group())
                    except json.JSONDecodeError:
                        pass

            insights: list[str] = data.get("insights", [])
            questions: list[str] = data.get("questions", [])

            # 第5步：存储巩固的见解
            for insight in insights[:3]:
                if insight and insight.strip():
                    await add_knowledge(
                        session,
                        topic="[睡眠整理]",
                        content=insight.strip(),
                        source="consolidation",   # ← 标记来源
                        confidence=85,            # ← 高置信度但低于100
                    )

            # 第6步：存储新的好奇问题
            for question in questions[:2]:
                if question and question.strip():
                    await add_pending_question(session, question.strip())

            # 第7步：提高复习知识的置信度
            insight_text = " ".join(insights).lower()
            for item in items:
                if item.topic.lower() in insight_text and item.confidence < 95:
                    item.confidence = min(100, item.confidence + 5)  # +5 但不超过100

            await session.commit()
            summary = "、".join(insights[:2]) if insights else ""
            logger.info(
                "Consolidation done — %d insights, %d questions.", 
                len(insights), 
                len(questions)
            )
        except Exception as exc:
            logger.exception("Memory consolidation error: %s", exc)
    return summary
```

### 睡眠状态管理

**文件**: [`server/ai/sleep.py`](server/ai/sleep.py#L237-L280)

```python
async def sleep_scheduler() -> None:
    """
    后台任务：每60秒检查是否需要睡眠/唤醒转换
    """
    if not settings.sleep_enabled:
        return

    logger.info(
        "Sleep scheduler started  (sleep=%02d:00  wake=%02d:00  tz=%s)",
        settings.sleep_hour,
        settings.wake_hour,
        settings.ai_timezone,
    )
    while True:
        try:
            hour = _local_now().hour
            async with async_session() as session:
                profile = await get_or_create_profile(session)
                is_sleeping = profile.is_sleeping

            # 检查是否到睡眠时间
            if not is_sleeping and hour == settings.sleep_hour:
                await go_to_sleep()
            
            # 检查是否到唤醒时间
            elif is_sleeping and hour == settings.wake_hour:
                await wake_up()

            await asyncio.sleep(60)  # 每60秒检查一次
        except Exception as exc:
            logger.exception("Sleep scheduler error: %s", exc)
            await asyncio.sleep(60)
```

### 巩固质量分析

| 方面 | 实现 | 评价 |
|------|------|------|
| **频率** | 每天晚上22:00 | ✅ 合理 |
| **样本量** | 最近30个知识项 | ✅ 足够 |
| **分析工具** | GPT-4o | ✅ 高质量 |
| **存储结果** | 新知识+新问题+摘要 | ✅ 完整 |
| **置信度增强** | +5分 | ⚠️ 增量略低 |
| **问题清理** | ❌ 无 | ⚠️ 问题堆积 |
| **错误恢复** | 后台任务处理 | ⚠️ 无重试 |

---

## 5️⃣ 缓存失效策略

### 缓存层架构

```
┌─────────────────────────────────────────────────┐
│            应用查询请求                          │
└────────────────────┬────────────────────────────┘
                     │
        ┌────────────v────────────┐
        │  _knowledge_cache       │ (内存字典)
        │  _confidence_cache      │ (应用级)
        │  TTL: 5分钟              │
        └────────────┬────────────┘
                     │ MISS (无缓存/过期)
        ┌────────────v────────────┐
        │  数据库查询               │ (持久化)
        │  KnowledgeItem表         │
        │  TTL: 无限               │
        └────────────┬────────────┘
                     │
        ┌────────────v────────────┐
        │  结果存入缓存             │
        │  格式: (timestamp, data)  │
        └─────────────────────────┘
```

### 5.1 缓存结构

**全局缓存定义** (`server/ai/tools.py:28-29`):
```python
_knowledge_cache: Dict[str, tuple] = {}      # Cache key → (time, data)
_confidence_cache: Dict[str, float] = {}     # Topic → confidence score
```

**缓存键生成**:
```python
cache_key = f"{topic}|{keywords}"  # 组合主题和关键词
# 例如: "Python|机器学习,深度学习"
```

### 5.2 缓存检查逻辑

```python
# 来自 server/ai/tools.py:_handle_knowledge_verify()
async def check_cache(topic: str, keywords: str) -> Optional[dict]:
    cache_key = f"{topic}|{keywords}"
    
    if cache_key in _knowledge_cache:
        cached_time, cached_data = _knowledge_cache[cache_key]
        import time
        
        # 检查是否过期
        if time.time() - cached_time < 300:  # ← 5分钟TTL
            logger.info(f"Cache hit: {cache_key}")
            return cached_data
        else:
            # ⚠️ 已过期但仍在字典中 - 不会自动删除！
            logger.debug(f"Cache expired: {cache_key}")
            # 继续查询数据库...
```

### 5.3 缓存更新

```python
# 查询数据库后更新缓存
result_data = {
    "found": True,
    "topic": topic,
    "count": len(knowledge_items),
    "knowledge_items": [...]
}

# 使用时间戳存储
_knowledge_cache[cache_key] = (
    __import__("time").time(),  # 当前时间戳
    result_data
)
```

### 5.4 缓存问题分析

```
╔═══════════════════════════════════════════════════════╗
║              缓存失效策略存在的问题                    ║
╠═══════════════════════════════════════════════════════╣
║ 1. 被动过期 (Lazy Expiration)                         ║
║    • 过期后不主动删除，仍占用内存                     ║
║    • 下次访问时才检查过期                             ║
║    → 长期运行可能导致内存泄漏                         ║
║                                                      ║
║ 2. 无界增长                                          ║
║    • 字典没有最大容量限制                             ║
║    • 新查询持续增加新KEY                              ║
║    • 如果查询多样化，内存无限增长                     ║
║                                                      ║
║ 3. 应用重启丢失                                      ║
║    • 内存缓存无持久化                                ║
║    • 应用重启后需从DB重新加载                         ║
║                                                      ║
║ 4. 多进程/协程安全性                                 ║
║    • 全局字典无锁保护                                ║
║    • 并发访问可能导致竞态条件                         ║
║                                                      ║
║ 5. 缓存预热问题                                      ║
║    • 每次重启需冷启动                                ║
║    • 首次查询会有延迟                                ║
╚═══════════════════════════════════════════════════════╝
```

### 5.5 改进建议

```python
# 方案1：LRU缓存（有限大小）
from functools import lru_cache

@lru_cache(maxsize=128)
async def get_cached_knowledge(topic: str, keywords: str):
    """自动限制缓存大小到128条"""
    return await search_knowledge(topic, keywords)

# 方案2：TTL缓存库
from cachetools import TTLCache
knowledge_cache = TTLCache(maxsize=256, ttl=300)  # 256条，5分钟TTL

# 方案3：后台清理任务
async def cache_cleanup_task():
    """定期清理过期缓存"""
    while True:
        current_time = time.time()
        expired_keys = [
            k for k, (t, _) in _knowledge_cache.items()
            if current_time - t > 300
        ]
        for key in expired_keys:
            del _knowledge_cache[key]
        await asyncio.sleep(60)  # 每分钟清理一次
```

---

## 6️⃣ 内存管理和垃圾回收

### 6.1 当前内存管理方案

```python
# 全局缓存（依赖Python GC）
_knowledge_cache: Dict[str, tuple] = {}      # ← 无主动清理
_confidence_cache: Dict[str, float] = {}      # ← 无主动清理

# 数据库连接池（异步）
engine = create_async_engine(settings.database_url, echo=False)
# ← SQLAlchemy自动管理连接

# 会话管理
async_session = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)
```

### 6.2 Python垃圾回收依赖

```python
# 缺少显式清理导致的问题
import gc

# ❌ 当前状况：完全被动
# • 当对象不再被引用时，Python GC才会清理
# • 缓存中的过期项目仍被保持引用
# • 长期运行可能导致内存泄漏

# ✅ 改进方案：主动清理
def cleanup_stale_cache():
    """主动清理过期缓存项"""
    current_time = time.time()
    stale_keys = []
    
    for key, (timestamp, data) in _knowledge_cache.items():
        if current_time - timestamp > 300:  # 5分钟过期
            stale_keys.append(key)
    
    for key in stale_keys:
        del _knowledge_cache[key]
        
    logger.info(f"Cleaned {len(stale_keys)} stale cache entries")

# 定期执行
async def memory_maintenance_task():
    while True:
        cleanup_stale_cache()
        gc.collect()  # 显式调用垃圾回收
        await asyncio.sleep(300)  # 每5分钟执行一次
```

### 6.3 数据库内存占用

| 表名 | 增长速度 | 没有清理时的影响 | 建议保留期 |
|------|---------|-----------------|-----------|
| conversations | 高 (每轮对话) | ⚠️ 严重 | 90天 |
| knowledge | 中 (学习产生) | ⚠️ 中等 | 无限 |
| pending_questions | 低 (每天1-2) | 低 | 已回答30天 |
| sleep_events | 极低 (每天2) | 低 | 已消费7天 |
| tools | 极低 (手动创建) | 极低 | 无限 |

### 6.4 建议的内存管理架构

```python
class MemoryManager:
    """统一的内存管理器"""
    
    def __init__(self):
        self.cache = TTLCache(maxsize=256, ttl=300)
        self.stats = {"hits": 0, "misses": 0, "evictions": 0}
    
    async def get_cached(self, key: str):
        """获取缓存，记录统计"""
        if key in self.cache:
            self.stats["hits"] += 1
            return self.cache[key]
        self.stats["misses"] += 1
        return None
    
    async def set_cached(self, key: str, value):
        """设置缓存"""
        if len(self.cache) >= self.cache.maxsize:
            self.stats["evictions"] += 1
        self.cache[key] = value
    
    async def cleanup_database(self, session):
        """定期清理数据库"""
        await cleanup_old_conversations(session, days=90)
        await cleanup_answered_questions(session)
        await cleanup_consumed_sleep_events(session)
        logger.info("Database cleanup completed")
    
    def get_stats(self):
        """获取内存统计"""
        return {
            **self.stats,
            "cache_size": len(self.cache),
            "hit_rate": self.stats["hits"] / (self.stats["hits"] + self.stats["misses"])
        }

# 使用
memory_manager = MemoryManager()

# 后台任务
async def memory_monitor():
    while True:
        # 每5分钟执行一次数据库清理
        async with async_session() as session:
            await memory_manager.cleanup_database(session)
        
        # 记录统计
        stats = memory_manager.get_stats()
        logger.info(f"Memory stats: {stats}")
        
        await asyncio.sleep(300)
```

---

## 7️⃣ 睡眠周期配置

**文件**: [`server/config.py`](server/config.py)

```python
class Settings(BaseSettings):
    # ── 睡眠周期 ──────────────────────────────
    
    # 启用/禁用睡眠功能
    sleep_enabled: bool = True
    
    # 睡眠时间 (24小时格式)
    sleep_hour: int = 22   # 晚上10点
    
    # 唤醒时间 (24小时格式)
    wake_hour: int = 7     # 早上7点
    
    # AI孩子的时区
    ai_timezone: str = "Asia/Shanghai"
```

**调度器启动** (`server/main.py:37-53`):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialising database …")
    await init_db()
    
    # 初始化睡眠状态 (基于当前时间)
    await initialize_sleep_state()
    
    # 启动睡眠调度器后台任务
    asyncio.create_task(sleep_scheduler())
    
    logger.info("AI Child server is ready.")
    yield
    logger.info("AI Child server shutting down.")
```

---

## 📈 数据增长模拟

假设系统运行1年，无清理机制：

```python
# 对话增长
# 假设：平均每天10轮对话，每轮2条消息
daily_conversations = 10 * 2    # 20条/天
yearly_conversations = 20 * 365 # 7,300条
size_gb = (7300 * 500) / (1024**3)  # 平均消息500字节
# → 年增长: ~3.5 MB

# 知识增长
# 假设：每天2个新知识项
daily_knowledge = 2
yearly_knowledge = 2 * 365      # 730条
size_mb = (730 * 2000) / (1024**2)  # 平均2KB/项
# → 年增长: ~1.4 MB

# 问题堆积
# 假设：每次睡眠生成2个新问题，每个问题平均回答时间14天
questions_answered_yearly = (365 / 14) * 2  # 52条
unanswered_overflow = 730 - 52   # 678条堆积
# → 年堆积: 678条未删除问题

# 睡眠事件
# 假设：每天2个事件 (睡眠+唤醒)
daily_sleep_events = 2
yearly_sleep_events = 2 * 365    # 730条
# → 无清理情况下: 730条堆积

# ⚠️ 总体: 3年后可能有 ~20,000+ 条无用数据
```

---

## 🎯 改进优先级

### 高优先级 (P0)

- [ ] **实现数据库清理策略**
  - 添加 `cleanup_old_conversations(days=90)`
  - 删除已回答超过30天的问题
  - 删除已消费的睡眠事件

- [ ] **改进缓存管理**
  - 使用 `cachetools.TTLCache` 替代简单字典
  - 限制缓存大小 (maxsize=256)
  - 添加缓存统计

### 中优先级 (P1)

- [ ] **添加内存监控**
  - 实现内存使用监控 API
  - 定期记录缓存效率
  - 告警机制 (内存超过阈值)

- [ ] **改进睡眠巩固**
  - 增加巩固频率检查
  - 实现巩固失败重试
  - 详细的巩固日志

### 低优先级 (P2)

- [ ] **数据迁移和归档**
  - 支持导出旧数据
  - 压缩历史对话
  - 支持数据库迁移

---

## 📋 核心函数速查表

| 函数 | 文件 | 行号 | 功能 | 是否有TTL |
|------|------|------|------|---------|
| `add_message()` | memory.py | 14-30 | 添加对话 | ❌ |
| `get_recent_messages()` | memory.py | 34-41 | 获取最近N条 | ⚠️ 仅软限制 |
| `add_knowledge()` | memory.py | 50-66 | 添加知识 | ❌ |
| `search_knowledge()` | memory.py | 81-90 | 搜索知识 | ❌ |
| `consolidate_memories()` | sleep.py | 150-240 | 睡眠巩固 | N/A |
| `go_to_sleep()` | sleep.py | 248-268 | 进入睡眠 | N/A |
| `wake_up()` | sleep.py | 271-288 | 唤醒 | N/A |
| `sleep_scheduler()` | sleep.py | 292-320 | 睡眠调度器 | N/A |

---

## 🔍 测试建议

```python
# 1. 缓存TTL测试
import time
from server.ai.tools import _knowledge_cache

async def test_cache_expiration():
    # 添加一个缓存项
    key = "test|keyword"
    _knowledge_cache[key] = (time.time(), {"data": "test"})
    
    # 立即检查 (应该命中)
    assert key in _knowledge_cache
    
    # 等待6分钟
    await asyncio.sleep(360)
    
    # 检查是否过期（被删除）
    # 当前实现：不会自动删除！

# 2. 数据增长测试
async def test_data_growth_over_time():
    """模拟长期运行的内存增长"""
    for day in range(365):
        # 每天添加20条对话
        for i in range(20):
            await add_message(session, "user", f"样本消息 {i}")
        
        # 检查表大小
        count = await count_messages(session)
        logger.info(f"Day {day}: {count} messages")

# 3. 睡眠巩固测试
async def test_sleep_consolidation():
    """测试睡眠巩固是否正常工作"""
    # 添加一些知识项
    for i in range(10):
        await add_knowledge(
            session, 
            topic=f"主题{i}",
            content=f"关于主题{i}的内容"
        )
    
    # 触发巩固
    summary = await consolidate_memories()
    
    # 验证巩固结果
    assert summary != ""
    
    # 检查是否生成了新问题
    questions = await get_unanswered_questions(session)
    assert len(questions) > 0
```

---

## 📚 相关文件导航

- [记忆管理](server/ai/memory.py)
- [睡眠管理](server/ai/sleep.py)
- [数据库模型](server/models/__init__.py)
- [工具和缓存](server/ai/tools.py)
- [配置](server/config.py)
- [防幻觉工具](server/ai/tools.py#L500-600)

---

## 🔗 关联研究

- [防幻觉工具实现报告](防幻觉工具实现报告.md)
- [学习机制深度研究](AI_CHILD_学习机制深度研究.md)
- [人格保存系统研究](AI_CHILD_人格保存系统研究.md)

---

**报告完成**: 2026-03-21  
**下一步**: 实现 P0 级改进（数据库清理）
