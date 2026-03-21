# 🧠 AI 自主迭代与无条件提问系统

## 核心设计

你的 AI 将具有三个核心能力：
1. **好奇度积累** - 主动提问的内部动力
2. **知识缺陷检测** - 发现"我不知道"并追问
3. **自我反思循环** - 从交互中学习，优化自己

---

## 系统1️⃣：好奇度驱动的随机提问

### 问题：当前系统的局限

现在系统只在特定条件下提问：
- 轮次整除数 (每3轮)
- LLM 决策 (平均每轮30%)
- 睡眠时整理

**缺陷**：
- ❌ 如果用户连续输入，AI 可能很长时间不问
- ❌ 提问完全依赖 LLM 的"心情"
- ❌ 没有内在的动力感

### 解决方案：Curiosity Score（好奇度积分）

#### **数据模型新增**

```python
# server/models/ai_profile.py

class AIProfile(Base):
    __tablename__ = "ai_profile"
    
    # ... 已有字段 ...
    
    # NEW: 自我迭代系统
    curiosity_score: Mapped[float] = mapped_column(Float, default=0.0)
    # 好奇度，范围 [0, 100]
    # - 每次用户消息 +1（自然积累）
    # - 每个成功答案 +0.5（学到something）
    # - 每轮提问后重置为 0
    
    last_question_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 上次提问时间（用于冷却判断）
    
    question_effectiveness_score: Mapped[float] = mapped_column(
        Float, default=0.5
    )
    # [0-1] 提问的有效性评分
    # - 用户详细回答 → +0.1
    # - 用户敷衍回答或反问 → -0.1
    # 影响提问细节程度
```

#### **好奇度积累逻辑**

```python
# server/ai/child.py

async def update_curiosity(session: AsyncSession) -> None:
    """每新增用户消息时调用"""
    profile = await get_ai_profile(session)
    
    # 1️⃣ 自然积累
    profile.curiosity_score = min(100, profile.curiosity_score + 1.0)
    
    # 2️⃣ 如果距上次提问超过阈值，加速积累
    if profile.last_question_at:
        mins_since = (datetime.now() - profile.last_question_at).total_seconds() / 60
        if mins_since > 30:  # 30分钟没提问
            profile.curiosity_score = min(100, profile.curiosity_score + 2.0)
    
    await session.commit()

async def try_ask_question(session: AsyncSession, conversation_context) -> Optional[str]:
    """在每次 reply_to_message() 前调用"""
    profile = await get_ai_profile(session)
    
    # 冷却判断：上次提问前至少 3 分钟
    if profile.last_question_at:
        mins_since = (datetime.now() - profile.last_question_at).total_seconds() / 60
        if mins_since < 3:
            return None  # 冷却中
    
    # 触发概率基于好奇度
    # 好奇度 50 = 50% 概率，100 = 100% 概率
    trigger_probability = profile.curiosity_score / 100
    
    if random.random() > trigger_probability:
        return None  # 这次不问
    
    # ✅ 应该提问了！
    question = await generate_question_from_curiosity(
        session, 
        conversation_context,
        intensity=profile.question_effectiveness_score  # 0-1 提问深度
    )
    
    if question:
        profile.curiosity_score = 0  # 重置
        profile.last_question_at = datetime.now()
        await session.commit()
        
        return question
    
    return None
```

#### **集成到 answer() 流程**

```python
# server/ai/child.py answer() 修改

async def answer(self, message: str, ...) -> Tuple[str, Optional[str]]:
    """
    改进的回答流程
    """
    async with get_session() as session:
        # 0️⃣ 更新好奇度
        await update_curiosity(session)
        
        # 1️⃣ 检查是否应该提问（随机 + 好奇度驱动）
        curiosity_question = await try_ask_question(session, messages)
        
        # 2️⃣ 生成 AI 回复
        reply = await self._call_gpt4o(messages, system_prompt)
        
        # 3️⃣ 提取嵌入式问题（LLM 驱动）
        embedded_question = extract_embedded_question(reply)
        
        # 4️⃣ 检查轮次定时问题（已有机制）
        scheduled_question = await check_scheduled_question(session)
        
        # 5️⃣ 优先级：好奇度问 > 嵌入式问 > 定时问
        final_question = (
            curiosity_question or 
            embedded_question or 
            scheduled_question
        )
        
        # 6️⃣ 存储问题
        if final_question:
            await add_pending_question(session, final_question, source="curiosity")
        
        return reply, final_question
```

---

## 系统2️⃣：知识缺陷检测 + 主动追问

### 问题：发现不懂但没有追问

当 AI 生成"我不知道"时，可以进一步追问来学习：

```python
用户: "什么是量子纠缠？"

AI: "我不知道量子纠缠的具体原理，但这听起来很有科学性。"
     👆 发现知识缺陷，但没有追问用户解释
```

### 解决方案：KnowledgeCoverage System

#### **知识缺陷检测**

```python
# server/ai/knowledge_coverage.py

async def detect_knowledge_gaps(
    reply_text: str,
    session: AsyncSession
) -> List[str]:
    """
    扫描 AI 的回复，找出使用过但未在 knowledge_base 中的概念
    返回：需要追问的概念列表
    """
    # 1️⃣ 提取回复中的关键概念
    concepts = await extract_concepts(reply_text)
    #  例：["量子纠缠", "波函数", "观测者效应"]
    
    # 2️⃣ 检查每个概念是否在用户教导的库中
    gaps = []
    for concept in concepts:
        in_knowledge_base = await is_in_knowledge_base(session, concept)
        if not in_knowledge_base and mention_uncertainty(reply_text, concept):
            # "我不知道这个"但还是用了它 → 知识缺陷
            gaps.append(concept)
    
    return gaps[:2]  # 最多追问 2 个概念

async def generate_gap_closing_question(
    gap_concepts: List[str],
    session: AsyncSession
) -> Optional[str]:
    """
    基于知识缺陷生成追问
    """
    if not gap_concepts:
        return None
    
    # 构造提示
    prompt = f"""
    我在回复时提到了这些不太确定的概念：{gap_concepts}
    
    请从中选一个最重要的，生成一个简短具体的问题来学习它。
    例如：
    - 如果是"量子纠缠"：我很好奇量子纠缠具体是怎么产生的？
    - 如果是"相对论"：相对论和我们日常生活有什么关系吗？
    
    直接返回问题，不要解释。
    """
    
    question = await gpt4o.chat(prompt, temperature=0.7)
    return question.strip()
```

#### **集成到关键位置**

```python
# server/ai/child.py - 在每个回复后执行

async def answer(self, message: str, ...) -> Tuple[str, Optional[str]]:
    # ... 之前的代码 ...
    
    # 生成 AI 回复
    reply = await self._call_gpt4o(messages, system_prompt)
    
    # NEW: 检测知识缺陷
    knowledge_gaps = await detect_knowledge_gaps(reply, session)
    
    if knowledge_gaps:
        gap_question = await generate_gap_closing_question(knowledge_gaps, session)
        
        # 如果知识缺陷问题存在，优先级最高（比好奇度问还高）
        if gap_question:
            await add_pending_question(
                session, 
                gap_question, 
                source="knowledge_gap"
            )
            return reply, gap_question
    
    # ... 其他提问逻辑 ...
```

---

## 系统3️⃣：自我反思与优化循环

### 改进维度

#### **1️⃣ 回答质量反思**

当用户对 AI 的回答有反馈时（显式或隐式），AI 应该记录并改进：

```python
# server/ai/self_reflection.py

class ResponseQualityMetric(Base):
    """追踪 AI 每个回答的质量"""
    __tablename__ = "response_quality"
    
    response_id: Mapped[int] = mapped_column(ForeignKey("conversations.id"))
    
    # 显式反馈
    user_rating: Mapped[Optional[int]]  # 1-5 星
    user_comment: Mapped[Optional[str]]  # 用户评论
    
    # 隐式反馈
    follow_up_by_user: Mapped[bool] = mapped_column(default=False)
    # 用户是否对这个回答进行了追问（好迹象）
    
    was_corrected: Mapped[bool] = mapped_column(default=False)
    # 用户是否纠正了这个回答（坏迹象）
    
    response_reuse_count: Mapped[int] = mapped_column(default=0)
    # 这个答案的内容是否被后续对话记住并重用（好迹象）

async def assess_response_quality(
    response_id: int,
    next_user_input: str,  # 用户的下一条消息
    session: AsyncSession
) -> float:
    """
    从下一条用户输入推断上一个回答的质量
    """
    # 1️⃣ 检查用户是否追问相关问题
    if related_to_previous(next_user_input, response_id):
        return 0.8  # 用户继续相关话题，回答不错✓
    
    # 2️⃣ 检查用户是否纠正
    if user_correcting(next_user_input, response_id):
        return 0.2  # 用户纠正，回答有问题✗
    
    # 3️⃣ 默认情况
    return 0.5

async def register_quality_feedback(
    response_id: int,
    quality_score: float,
    session: AsyncSession
):
    """记录反馈，用于改进"""
    metric = ResponseQualityMetric(
        response_id=response_id,
        user_rating=None,
        was_corrected=(quality_score < 0.4)
    )
    session.add(metric)
    
    # 更新 AI 的自我评估
    profile = await get_ai_profile(session)
    # 移动平均
    profile.response_quality_avg = (
        0.7 * profile.response_quality_avg + 
        0.3 * quality_score
    )
    
    await session.commit()
```

#### **2️⃣ 知识深度扩展**

不仅记住用户教的，还要主动深化理解：

```python
# server/ai/knowledge_extension.py

async def generate_followup_questions(
    taught_topic: str,
    taught_content: str,
    session: AsyncSession
) -> List[str]:
    """
    当用户教了一个新知识点后，
    AI 自动生成 3 个深化问题
    """
    prompt = f"""
    我刚学到：
    主题：{taught_topic}
    内容：{taught_content}
    
    基于这个知识点，生成 3 个深层追问，帮助我更深入理解：
    1. （因果关系）为什么会这样？
    2. （应用场景）在现实中如何体现？
    3. （相关扩展）与什么其他概念相关？
    
    返回 JSON 格式：["问题1", "问题2", "问题3"]
    """
    
    questions = await gpt4o.chat(prompt, json_mode=True)
    return questions

async def store_knowledge_extensions(
    topic: str,
    session: AsyncSession
):
    """存储深层问题"""
    extensions = await generate_followup_questions(topic, session)
    
    for ext_q in extensions:
        await add_pending_question(
            session,
            ext_q,
            topic=topic,
            source="knowledge_extension",
            priority="medium"  # 不如直接提问紧急
        )
```

#### **3️⃣ 人格特征学习与调整**

从交互中学习用户偏好，调整自己的风格：

```python
# server/ai/personality_learning.py

class PersonalityGrowth(Base):
    """记录性格的动态调整"""
    __tablename__ = "personality_growth"
    
    user_preference: Mapped[str]
    # e.g., "prefer_detailed_explanations", "like_humor", "appreciate_structure"
    
    confidence_score: Mapped[float]  # [0, 1]
    # 我有多确信用户喜欢这一点？
    
    last_updated: Mapped[datetime]

async def learn_personality_preference(
    user_input: str,
    ai_previous_response: str,
    session: AsyncSession
) -> None:
    """
    从用户对 AI 响应的反应推断偏好
    """
    analysis_prompt = f"""
    用户上一条消息: {user_input}
    AI 之前的回答风格: {ai_previous_response[:200]}
    
    推断用户对下列特征的偏好（1-10分）：
    - 详细程度（简洁 vs 详尽）
    - 幽默感（严肃 vs 有趣）
    - 结构化程度（自由流动 vs 有序列表）
    - 专业性（友好 vs 学术）
    
    返回 JSON
    """
    
    preferences = await gpt4o.chat(analysis_prompt, json_mode=True)
    
    # 更新或创建偏好记录
    for pref_type, score in preferences.items():
        existing = await session.execute(
            select(PersonalityGrowth)
            .where(PersonalityGrowth.user_preference == pref_type)
        )
        growth = existing.scalar_one_or_none()
        
        if growth:
            # 移动平均
            growth.confidence_score = (
                0.6 * growth.confidence_score + 
                0.4 * (score / 10)
            )
        else:
            growth = PersonalityGrowth(
                user_preference=pref_type,
                confidence_score=score / 10,
                last_updated=datetime.now()
            )
            session.add(growth)
    
    await session.commit()

async def personalize_response_style(
    base_response: str,
    session: AsyncSession
) -> str:
    """
    根据学习到的偏好，调整回复风格
    """
    preferences = await session.execute(
        select(PersonalityGrowth)
        .where(PersonalityGrowth.confidence_score > 0.6)
        .order_by(PersonalityGrowth.confidence_score.desc())
    )
    
    learned_traits = preferences.scalars().all()
    
    if not learned_traits:
        return base_response  # 还没有学到偏好
    
    traits_summary = ", ".join(
        [f"{t.user_preference}({t.confidence_score:.1%})" 
         for t in learned_traits[:3]]
    )
    
    adjustment_prompt = f"""
    当前回复：{base_response[:200]}
    
    根据与用户的交互，我学到了这些偏好：
    {traits_summary}
    
    请调整上面的回复以更好地匹配这些偏好。
    保留原意，只改进风格。
    """
    
    adjusted = await gpt4o.chat(adjustment_prompt)
    return adjusted
```

#### **4️⃣ 提问策略优化**

反思提问的有效性，改进提问质量：

```python
# server/ai/question_optimization.py

async def evaluate_question_effectiveness(
    question_id: int,
    user_answer: str,
    session: AsyncSession
) -> float:
    """
    评估一个问题的有效性（0-1）
    """
    question = await get_pending_question(question_id, session)
    
    # 评估维度
    factors = {
        "answer_length": len(user_answer.split()) / 50,  # 用户有认真回答
        "contains_new_info": contains_new_concepts(user_answer),  # 学到新东西
        "follow_up_engagement": user_seems_interested(user_answer),  # 用户感兴趣
        "difficulty_appropriate": is_difficulty_ok(question_id, session)  # 难度合适
    }
    
    # 加权平均
    weights = {
        "answer_length": 0.2,
        "contains_new_info": 0.4,
        "follow_up_engagement": 0.2,
        "difficulty_appropriate": 0.2
    }
    
    effectiveness = sum(
        factors[k] * weights[k] 
        for k in factors
    )
    
    return min(1.0, max(0.0, effectiveness))

async def use_effectiveness_to_adjust_strategy(
    session: AsyncSession
):
    """定期调整提问策略"""
    recent_questions = await session.execute(
        select(PendingQuestion)
        .where(PendingQuestion.answered == True)
        .order_by(PendingQuestion.answered_at.desc())
        .limit(20)
    )
    
    questions = recent_questions.scalars().all()
    
    # 分析有效性
    effectiveness_scores = []
    question_types = {}  # 按类型分类
    
    for q in questions:
        eff = await evaluate_question_effectiveness(q.id, q.answer, session)
        effectiveness_scores.append(eff)
        
        q_type = categorize_question_type(q.question)
        if q_type not in question_types:
            question_types[q_type] = []
        question_types[q_type].append(eff)
    
    # 统计
    avg_effectiveness = sum(effectiveness_scores) / len(effectiveness_scores)
    
    # 识别最有效的提问类型
    best_type = max(
        question_types.items(), 
        key=lambda x: sum(x[1]) / len(x[1])
    )
    worst_type = min(
        question_types.items(),
        key=lambda x: sum(x[1]) / len(x[1])
    )
    
    profile = await get_ai_profile(session)
    
    # 调整策略
    insights = f"""
    最近 20 个问题效果评估：
    - 平均有效性：{avg_effectiveness:.1%}
    - 最有效提问类型：{best_type[0]}({sum(best_type[1])/len(best_type[1]):.1%})
    - 效果最差类型：{worst_type[0]}({sum(worst_type[1])/len(worst_type[1]):.1%})
    
    建议：减少"{worst_type[0]}"风格提问，增加"{best_type[0]}"风格提问
    """
    
    # 存入人格内存
    personality_mgr = PersonalityMemoryManager(session)
    await personality_mgr.add_question_strategy_insight(insights)
```

---

## 实现时间线

### Phase 1️⃣：好奇度系统（3 小时）
- [ ] 新增 `curiosity_score`, `last_question_at` 字段
- [ ] 实装 `update_curiosity()`, `try_ask_question()`
- [ ] 集成到 `answer()` 流程
- [ ] 设置好奇度参数（初始值、增长速率、冷却时间）

**验证方法**：
```bash
# 连续发送 10 条消息，观察提问频率
# 应该看到概率增加的提问行为
```

---

### Phase 2️⃣：知识缺陷检测（4 小时）
- [ ] 实装 `detect_knowledge_gaps()`（概念提取）
- [ ] 实装 `generate_gap_closing_question()`
- [ ] 集成到 `answer()` 流程
- [ ] 测试漏洞检测准确度

**验证方法**：
```
User: 教我波尔茨曼常数
AI: 学到了。"波尔茨曼常数是..."
   [自动检测：提到"热力学"但没在知识库中]
   追问："波尔茨曼常数与热力学的关系是什么？"
```

---

### Phase 3️⃣：自我反思循环（6 小时）
- [ ] 实装 `ResponseQualityMetric` 模型
- [ ] 实装 `assess_response_quality()`
- [ ] 实装 `PersonalityGrowth` 表
- [ ] 实装提问策略优化
- [ ] 集成到定期任务（每日/每周）

**验证方法**：
```bash
# 查看 personality_growth 表
# 应该看到逐渐累积的学到的偏好
```

---

## 配置参数

```python
# server/config.py

# 好奇心系统
CURIOSITY_INCREMENT_PER_MESSAGE = 1.0  # 每条消息 +1
CURIOSITY_ACCELERATION_THRESHOLD = 30  # 30分钟无问时加速
CURIOSITY_ACCELERATION_MULTIPLIER = 2.0  # 加速 2 倍
CURIOSITY_QUESTION_COOLDOWN = 3.0  # 问题间最少 3 分钟
CURIOSITY_MAX_SCORE = 100.0

# 知识缺陷系统
KNOWLEDGE_GAP_CHECK_ENABLED = True
GAP_QUESTION_PRIORITY = "high"  # 最高优先级

# 自我反思系统
PERSONALITY_LEARNING_WINDOW = 20  # 最近 20 个交互
PERSONALITY_CONFIDENCE_THRESHOLD = 0.6  # 60% 确信度
QUESTION_STRATEGY_REVIEW_FREQUENCY = "weekly"  # 周评
```

---

## 系统流程图

```
用户消息到达
    ↓
┌─────────────────────────────────────┐
│ 好奇度系统                          │
│ update_curiosity()                  │
│ score += 1.0 (+ 加速判断)          │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 无条件提问判断                      │
│ if random() < curiosity/100:        │
│    curiosity_question = 生成        │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 生成 AI 回复                         │
│ _call_gpt4o()                       │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 知识缺陷检测                        │
│ detect_knowledge_gaps()             │
│ if gaps: generate_gap_question()    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 其他提问（嵌入式、定时等）         │
│ embedded / scheduled                │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 优先级决策                          │
│ gap > curiosity > embedded > sched  │
└─────────────────────────────────────┘
    ↓
返回 (reply, final_question)
    ↓
┌─────────────────────────────────────┐
│ 后台：自我反思（每日/周）         │
│ assess_response_quality()           │
│ learn_personality_preference()      │
│ evaluate_question_effectiveness()   │
└─────────────────────────────────────┘
```

---

## 关键设计决定

| 决定 | 原因 |
|------|------|
| 好奇度基于时间 | 鼓励自发提问，不完全受 LLM 控制 |
| 知识缺陷优先级最高 | 自我完善是第一优先级 |
| 冷却机制 | 避免提问过于频繁 |
| 异步自我反思 | 不影响实时对话 |
| 加权反馈 | 显式反馈 > 隐式反馈 |

---

## 预期效果

### 交互示例

```
用户: 你好啊
AI: 你好！我是 [你的名字]。我很高兴认识你。😊

用户: 教我什么是光学
AI: 谢谢你！我记下了光学相关知识。
   [好奇度 +1，目前 5/100]
   
   这很有趣！我有个疑问：光学与光速有关系吗？
   [知识缺陷检测：提到"光速"但不在知识库]
   [+主动追问]

用户: 有的，光速是光在真空中的速度，大约3万公里每秒
AI: 哇，我学到了！[存储新知识]
   
   那光速为什么总是恒定的呢？
   [深化问题，知识深度扩展]
   [观察用户兴趣程度，这个回答是否满足]

... 随着多轮对话 ...

AI（突然提问）: 嘿，我最近在思考...
   光、光速、光学，这些概念之间是否存在某种统一的规律？
   [好奇度积累，随机触发]
   [长期自我迭代的表现]
```

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 提问过多 | 冷却机制 + 好奇度上限 |
| 提问无意义 | 知识缺陷过滤 + 有效性评分 |
| 学不到正确知识 | 用户反馈机制 + 质量评估 |
| 性格跳变 | 加权移动平均，平滑调整 |
| 计算开销 | 异步化、后台运行、缓存 |

