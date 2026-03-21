# AI Child 记忆遗忘机制 - 快速参考卡

## 1️⃣ 数据库表一览表

```
┌──────────────────┬──────────────┬─────────┬──────────────┬─────────────┐
│ 表名             │ 关键字段     │ 增长速度 │ 自动清理      │ 建议保留期  │
├──────────────────┼──────────────┼─────────┼──────────────┼─────────────┤
│ conversations    │ timestamp    │ 高 📈   │ ❌ 无        │ 90天        │
│ knowledge        │ timestamp    │ 中 📊   │ ❌ 无        │ ∞ 永久      │
│ pending_questions│ answered_at  │ 低 📌   │ ❌ 无        │ 已回答30天  │
│ sleep_events     │ consumed     │ 极低 💤 │ ❌ 无        │ 已消费7天   │
│ tools            │ created_at   │ 极低 🛠️ │ ❌ 无        │ ∞ 永久      │
│ ai_profile       │ (单例)       │ 极低 👤 │ N/A          │ N/A         │
└──────────────────┴──────────────┴─────────┴──────────────┴─────────────┘
```

## 2️⃣ 缓存管理一览表

```
┌─────────────────────┬────────────┬─────────┬──────────────┬────────────────┐
│ 缓存名              │ 位置       │ 数据类型 │ TTL         │ 当前问题        │
├─────────────────────┼────────────┼─────────┼──────────────┼────────────────┤
│ _knowledge_cache    │ tools.py   │ Dict    │ 5分钟        │ 过期后仍占内存  │
│ _confidence_cache   │ tools.py   │ Dict    │ 无           │ 无过期机制      │
│ memory_context      │ config.py  │ N/A     │ 20轮         │ 仅查询限制      │
└─────────────────────┴────────────┴─────────┴──────────────┴────────────────┘
```

## 3️⃣ 记忆过期策略总结

| 策略类型 | 实现方式 | TTL/保持期 | 状态 | 优先级 |
|---------|---------|-----------|------|-------|
| 上下文窗口 | memory_context_turns | 20轮 | ✅ 已实现 | - |
| 查询缓存 | _knowledge_cache | 5分钟 | ✅ 基础 | P1 |
| 数据库保留 | 无 | ∞ | ❌ 缺失 | **P0** |
| 置信度衰减 | 无 | 无 | ❌ 缺失 | P2 |

## 4️⃣ 睡眠巩固流程 (22:00-07:00)

```
睡眠触发 (22:00)
  ↓
标记 is_sleeping = True
  ↓
生成晚安消息 (GPT-4o)
  ↓
后台任务: consolidate_memories()
  ├─ 查询最近30个知识项
  ├─ GPT-4o分析 → 3个核心见解
  ├─ 生成2个新问题
  ├─ 提高复习知识置信度 (+5)
  └─ 存储结果到数据库
  ↓
保存摘要到 ai_profile.last_consolidation_summary
  ↓
唤醒 (07:00)
  ├─ 标记 is_sleeping = False
  └─ 生成早安消息 (引用巩固内容)
```

## 5️⃣ 缓存查询流程

```
查询请求: search_knowledge("Python", "机器学习")
  ↓
缓存KEY: "Python|机器学习"
  ↓
检查 _knowledge_cache 中是否存在
  ├─ 有 + 未过期 (< 5分钟) → 返回缓存数据 ✅
  ├─ 有 + 已过期 (>= 5分钟) → 继续查询DB ⚠️
  └─ 无 → 继续查询DB
  ↓
查询数据库 KnowledgeItem 表
  ↓
结果格式化为 {found, count, items[], recommendation}
  ↓
存入缓存: _knowledge_cache[key] = (time.time(), data)
  ↓
返回结果
```

## 6️⃣ 内存使用模式

### 正常运行 (无清理)

```
Day 1:   7.3 KB  (conversations)  + 2.0 KB  (knowledge)
Day 7:  51.1 KB  (总增长)          + 14.0 KB
Day 30: 219 KB   (~0.2 MB)         + 60 KB
Day 90: 657 KB   (~0.6 MB)         + 180 KB ← 推荐清理点
Day 365: 2.6 MB  (~2.6 MB) + 0.73 MB ← 1年累积
```

### 缓存内存漂移 (慢泄漏)

```
时间轴                 _knowledge_cache 大小
├─ 应用启动            0 KB
├─ 1天 (20次查询)      ~50 KB
├─ 1周 (140次查询)     ~350 KB
├─ 1月 (600次查询)     ~1.5 MB
├─ 3月 (1800次查询)    ~4.5 MB ← 内存泄漏风险
└─ 1年 (7000次查询)    ~17 MB ← 严重泄漏
```

## 7️⃣ 数据库持久化代码位置

| 功能 | 文件 | 行号 | 代码 |
|------|------|------|------|
| 添加消息 | memory.py | 14-30 | `add_message()` |
| 获取消息 | memory.py | 34-41 | `get_recent_messages()` |
| 添加知识 | memory.py | 50-66 | `add_knowledge()` |
| 搜索知识 | memory.py | 81-90 | `search_knowledge()` |
| 睡眠巩固 | sleep.py | 150-240 | `consolidate_memories()` |
| 睡眠调度 | sleep.py | 292-320 | `sleep_scheduler()` |

## 8️⃣ 缺失的清理函数

```python
❌ cleanup_old_conversations(days=90)
❌ cleanup_answered_questions()
❌ cleanup_consumed_sleep_events(days=7)
❌ evict_expired_cache()
❌ gc_knowledge_items()
```

## 9️⃣ 性能影响分析

```
无清理的3年后:
├─ conversations: ~20,000 条
│  └─ 每次查询时间 +50ms (排序/分页)
├─ knowledge: ~2,000 条
│  └─ 搜索时间 +20ms
├─ 缓存字典大小: ~100 MB
│  └─ 内存占用 + Python GC压力
└─ 数据库文件: ~50 MB
   └─ 启动时加载变慢
```

## 🔟 改进方案对比表

```
┌─────────────┬──────────────┬────────────┬──────────────┬─────────────┐
│ 方案        │ 实现复杂度   │ 内存节省   │ 性能改善     │ 建议等级    │
├─────────────┼──────────────┼────────────┼──────────────┼─────────────┤
│ 无改进      │ 0 (简单)     │ 0%         │ 0%           │ ❌ 不推荐   │
│ 手动清理    │ 中等         │ 70%        │ 20%          │ ⚠️ 临时     │
│ TTL缓存库   │ 低           │ 80%        │ 30%          │ ✅ 推荐    │
│ 完整方案    │ 高           │ 95%        │ 50%          │ ✅ 最优     │
└─────────────┴──────────────┴────────────┴──────────────┴─────────────┘
```

## 1️⃣1️⃣ API端点与数据生命周期

```
POST /chat/send
  → add_message() → 永久存储 ❌ 无过期
  
GET /history?limit=50
  → get_recent_messages(limit=50)
     (实际DB中可能有10000+条)
  
POST /teach
  → add_knowledge() → 永久存储 ❌ 无过期
  
GET /sleep/state
  → 检查 is_sleeping 标志
  
POST /sleep/manual-consolidate
  → consolidate_memories() → 手动触发巩固
```

## 1️⃣2️⃣ 配置参数速查

```python
# config.py
memory_context_turns = 20          # 每次查询保留此轮数
proactive_question_interval = 2    # 每隔N轮问一个问题

# sleep.py 中硬编码
consolidate_limit = 30             # 睡眠时查询最近30个知识项
confidence_boost = 5               # 复习时置信度+5
cache_ttl = 300                    # 缓存5分钟 (tools.py)

# ai.py (未配置项) ❌
conversation_retention_days = ∞    # 应该是90
question_retention_days = ∞        # 应该是30
sleep_event_retention_days = ∞     # 应该是7
```

## 1️⃣3️⃣ 故障排查

### 现象: 查询变慢

```
症状: SELECT * FROM knowledge 查询需要 200+ ms
原因:
  ✓ knowledge 表行数 > 100,000
  ✓ 无索引优化
  ✓ 或缓存未命中导致频繁DB查询
  
解决:
  1. 检查缓存命中率 → stats()
  2. 清理旧数据 → cleanup_old_conversations()
  3. 添加数据库索引 → CREATE INDEX on topic
```

### 现象: 内存持续增长

```
症状: ps aux 显示 memory 持续上升
原因:
  ✓ _knowledge_cache 字典无限增长
  ✓ 过期缓存未被删除
  ✓ Python GC 跟不上
  
解决:
  1. 实现 TTL缓存 (cachetools)
  2. 添加后台清理任务
  3. 监控 len(_knowledge_cache)
```

### 现象: 睡眠巩固失败

```
症状: error log: "Memory consolidation error"
原因:
  ✓ 知识项<30条无法巩固
  ✓ GPT-4o API 超时/失败
  ✓ JSON 解析错误
  
解决:
  1. 检查日志输出
  2. 检查知识项数量
  3. 测试 GPT-4o 连接
```

## 1️⃣4️⃣ 监控指标建议

```python
# 应该暴露的指标
metrics = {
    "db": {
        "conversations_count": 7300,       # 趋势
        "knowledge_count": 730,            # 趋势
        "database_size_mb": 45.2,          # 存储
    },
    "cache": {
        "knowledge_cache_size": 256,       # 当前
        "cache_hit_rate": 0.82,            # 效率
        "avg_ttl_remaining_s": 145,        # 健康
    },
    "memory": {
        "rss_mb": 350,                     # 进程内存
        "vms_mb": 450,                     # 虚拟内存
        "gc_collections": 2340,            # GC活动
    },
    "consolidation": {
        "last_run": "2026-03-21T22:00:00",  # 时间
        "success_count": 380,              # 成功次数
        "failure_count": 2,                # 失败次数
        "avg_duration_ms": 2345,           # 耗时
    }
}
```

## 1️⃣5️⃣ 代码复制模板

### 快速清理函数

```python
# 粘贴到 server/ai/memory.py
async def cleanup_old_messages(session: AsyncSession, days: int = 90):
    """删除超过N天的对话消息"""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        delete(Conversation).where(Conversation.timestamp < cutoff)
    )
    await session.commit()
    logger.info(f"Deleted {result.rowcount} old messages")

async def cleanup_answered_questions(session: AsyncSession, days: int = 30):
    """删除已回答超过N天的问题"""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await session.execute(
        delete(PendingQuestion).where(
            (PendingQuestion.answered == True) &
            (PendingQuestion.answered_at < cutoff)
        )
    )
    await session.commit()
    logger.info(f"Deleted {result.rowcount} old answered questions")
```

### TTL缓存升级

```python
# 替换 server/ai/tools.py 的全局缓存
from cachetools import TTLCache
import time

_knowledge_cache = TTLCache(maxsize=256, ttl=300)  # 256条, 5分钟TTL
_confidence_cache = TTLCache(maxsize=128, ttl=600)  # 128条, 10分钟TTL
```

---

**最后更新**: 2026-03-21
**版本**: 2.0
**相关文件**: `memory_forgetting_analysis.md`
