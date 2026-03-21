"""
🧠 自主迭代系统 — 码实现代码

这个文件包含了三个系统的核心实现，可以直接集成到项目中。
"""

# ============================================================================
# Part 1️⃣: 数据模型扩展
# ============================================================================

# 文件: server/models/__init__.py（新增字段）

from typing import Optional
from datetime import datetime
from sqlalchemy import Float, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column


# 扩展 AIProfile 模型
class AIProfile:
    """ADD THESE FIELDS TO EXISTING AIProfile CLASS"""
    
    # 好奇度系统
    curiosity_score: Mapped[float] = mapped_column(
        Float, 
        default=0.0,
        comment="当前好奇度 [0-100]"
    )
    
    last_question_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True,
        comment="上次提问时间"
    )
    
    question_effectiveness_score: Mapped[float] = mapped_column(
        Float,
        default=0.5,
        comment="提问有效性评分 [0-1]，影响提问深度"
    )
    
    response_quality_avg: Mapped[float] = mapped_column(
        Float,
        default=0.5,
        comment="平均回答质量评分"
    )


# ============================================================================
# Part 2️⃣: 好奇度系统核心实现
# ============================================================================

# 文件: server/ai/curiosity_engine.py（新建）

import random
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import AIProfile, PendingQuestion


async def update_curiosity(session: AsyncSession) -> float:
    """
    每新增用户消息时调用，更新好奇度积分
    
    Returns: 当前好奇度分数
    """
    profile = await get_ai_profile(session)
    
    # 基础积累：每条消息 +1
    profile.curiosity_score = min(100, profile.curiosity_score + 1.0)
    
    # 加速机制：如果长时间没提问，加速积累
    if profile.last_question_at is not None:
        time_since_question = datetime.utcnow() - profile.last_question_at
        minutes_passed = time_since_question.total_seconds() / 60
        
        if minutes_passed > 30:  # 30 分钟没提问
            acceleration = min(5.0, minutes_passed / 10)  # 最多加 5.0
            profile.curiosity_score = min(100, profile.curiosity_score + acceleration)
    
    await session.commit()
    return profile.curiosity_score


async def try_ask_question(
    session: AsyncSession,
    conversation_context: list,
    ai_name: str
) -> Optional[str]:
    """
    根据好奇度随机决定是否提问
    
    Args:
        session: 数据库会话
        conversation_context: 对话历史列表
        ai_name: AI 的名字
    
    Returns:
        生成的问题，或 None
    """
    profile = await get_ai_profile(session)
    
    # 冷却检查：上次提问后至少等待 3 分钟
    if profile.last_question_at is not None:
        time_since = (datetime.utcnow() - profile.last_question_at).total_seconds() / 60
        if time_since < 3:
            return None  # 冷却中，不提问
    
    # 基于好奇度的提问概率
    # 好奇度 0 = 0% 提问，50 = 50%, 100 = 100%
    trigger_probability = profile.curiosity_score / 100.0
    
    if random.random() > trigger_probability:
        return None  # 这次不幸运，没有提问
    
    # ✅ 决定提问了！
    print(f"🧠 好奇度触发提问 (得分: {profile.curiosity_score:.1f})")
    
    # 生成问题（调用 GPT-4o）
    from ai.child import AIChild
    child = AIChild(ai_name)
    
    question = await child._generate_proactive_question(
        conversation_context,
        relevant_knowledge=[],  # 可传入相关知识
        name=ai_name,
        intensity=profile.question_effectiveness_score
    )
    
    if question:
        # 重置好奇度，记录提问时间
        profile.curiosity_score = 0
        profile.last_question_at = datetime.utcnow()
        await session.commit()
        
        return question
    
    return None


async def get_ai_profile(session: AsyncSession) -> AIProfile:
    """获取 AI 档案"""
    result = await session.execute(select(AIProfile).limit(1))
    return result.scalar_one_or_none()


# ============================================================================
# Part 3️⃣: 知识缺陷检测系统
# ============================================================================

# 文件: server/ai/knowledge_coverage.py（新建）

from typing import List
import json
from openai import AsyncOpenAI

from config import settings
from models import KnowledgeItem


async def detect_knowledge_gaps(
    reply_text: str,
    session: AsyncSession
) -> List[str]:
    """
    检测 AI 回复中提到但未在知识库中学过的概念
    
    Returns: 知识缺陷概念列表
    """
    
    # 使用 GPT-4o 提取关键概念
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    extraction_prompt = f"""
    从下面的文本中提取 3-5 个关键概念或专有名词：
    
    文本：{reply_text}
    
    返回 JSON 格式：{{"concepts": ["概念1", "概念2", ...]}}
    """
    
    extract_response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": extraction_prompt}],
        temperature=0.3,
    )
    
    try:
        concepts_data = json.loads(extract_response.choices[0].message.content)
        concepts = concepts_data.get("concepts", [])
    except (json.JSONDecodeError, KeyError):
        return []
    
    # 检查每个概念是否在用户教导的知识库中
    gaps = []
    
    for concept in concepts:
        # 查询知识库
        result = await session.execute(
            select(KnowledgeItem)
            .where(KnowledgeItem.topic.ilike(f"%{concept}%"))
            .limit(1)
        )
        
        if result.scalar_one_or_none() is None:
            # 这个概念不在知识库中
            # 检查是否在回复中有不确定的用语
            if _has_uncertainty_marker(reply_text, concept):
                gaps.append(concept)
    
    return gaps[:2]  # 最多返回 2 个缺陷


def _has_uncertainty_marker(text: str, concept: str) -> bool:
    """检查是否在提到概念时带有不确定的用语"""
    uncertainty_words = [
        "我不知道", "不确定", "可能", "据我可知", "我听说过",
        "听起来", "如果我没记错", "大概", "似乎", "好像"
    ]
    
    # 简单的启发式方法：在概念附近是否有不确定用语
    concept_lower = concept.lower()
    text_lower = text.lower()
    
    if concept_lower not in text_lower:
        return False
    
    # 检查附近的不确定用语
    idx = text_lower.find(concept_lower)
    context_start = max(0, idx - 80)
    context_end = min(len(text), idx + len(concept) + 80)
    context = text[context_start:context_end].lower()
    
    return any(marker in context for marker in uncertainty_words)


async def generate_gap_closing_question(
    gap_concepts: List[str],
    conversation_context: list
) -> Optional[str]:
    """
    根据知识缺陷生成追问
    """
    if not gap_concepts:
        return None
    
    # 优先选择第一个缺陷
    concept = gap_concepts[0]
    
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    context_str = "\n".join([
        f"{m['role']}: {m['content'][:100]}"
        for m in conversation_context[-4:]  # 最近 4 条消息
    ])
    
    prompt = f"""
    在我们的对话中，有一个我不太确定的概念："{concept}"
    
    最近的对话：
    {context_str}
    
    请从我的角度生成一个简短、具体的问题来更好地理解"{concept}"。
    问题应该：
    1. 简洁（1 句话）
    2. 具体（不是泛泛而谈）
    3. 表现出真实的好奇心
    4. 基于我们的对话语境
    
    直接返回问题，不要解释。最多 20 个字。
    """
    
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=50
    )
    
    question = response.choices[0].message.content.strip()
    return question if question else None


# ============================================================================
# Part 4️⃣: 集成到 answer() 主流程
# ============================================================================

# 文件: server/ai/child.py（修改 answer() 方法）

"""
在 AIChild.answer() 方法中的改动（参考位置）：

async def answer(
    self,
    message: str,
    chat_id: str,
    session: AsyncSession
) -> Tuple[str, Optional[str]]:
    
    # ... 现有代码 ...
    
    # 💡 新增：Step 0.5 - 更新好奇度并尝试提问
    from ai.curiosity_engine import update_curiosity, try_ask_question
    from ai.knowledge_coverage import detect_knowledge_gaps, generate_gap_closing_question
    
    await update_curiosity(session)
    curiosity_question = await try_ask_question(session, messages, self.name)
    
    # 生成 AI 回复
    reply_text = await self._call_gpt4o(messages, system_prompt)
    
    # 💡 新增：Step 5.5 - 检测知识缺陷
    knowledge_gaps = await detect_knowledge_gaps(reply_text, session)
    gap_question = None
    
    if knowledge_gaps:
        print(f"🔍 检测到知识缺陷: {knowledge_gaps}")
        gap_question = await generate_gap_closing_question(
            knowledge_gaps,
            messages
        )
    
    # 提取嵌入式问题（现有逻辑）
    embedded_question = extract_embedded_question(reply_text)
    
    # 💡 优先级：知识缺陷 > 好奇度 > 嵌入式 > 定时
    final_question = (
        gap_question or
        curiosity_question or
        embedded_question or
        await check_scheduled_question(session)
    )
    
    # 存储问题
    if final_question:
        source = "knowledge_gap" if gap_question else (
            "curiosity" if curiosity_question else (
                "embedded" if embedded_question else "scheduled"
            )
        )
        await add_pending_question(session, final_question, source=source)
        print(f"❓ 生成提问 [{source}]: {final_question}")
    
    return reply_text, final_question
"""


# ============================================================================
# Part 5️⃣: 自我反思系统（可选，高级）
# ============================================================================

# 文件: server/ai/self_reflection.py（新建，可选）

from datetime import datetime, timedelta
from sqlalchemy import select, func


async def evaluate_response_quality(
    ai_response: str,
    user_follow_up: str,
    session: AsyncSession
) -> float:
    """
    从用户的下一条输入推断上一个 AI 回答的质量
    
    Returns: 质量分数 [0, 1]
    """
    
    # 因素 1: 用户是否继续相关话题？
    relevance_score = _calculate_topic_relevance(ai_response, user_follow_up)
    
    # 因素 2: 用户是否表达满意或感谢？
    satisfaction_score = _detect_satisfaction(user_follow_up)
    
    # 因素 3: 用户是否纠正了 AI？
    correction_score = _detect_correction(user_follow_up)
    
    # 加权平均
    quality = (
        0.5 * relevance_score +
        0.3 * satisfaction_score +
        0.2 * (1.0 - correction_score)  # 纠正是负面信号
    )
    
    return min(1.0, max(0.0, quality))


def _calculate_topic_relevance(text1: str, text2: str) -> float:
    """简单的相关性检查"""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 or not words2:
        return 0.5
    
    # Jaccard 相似度
    intersection = len(words1 & words2)
    union = len(words1 | words2)
    
    return intersection / union if union > 0 else 0.5


def _detect_satisfaction(text: str) -> float:
    """检测用户是否满意"""
    positive_markers = [
        "谢谢", "太好了", "太棒了", "完美", "有帮助", "明白了",
        "很有用", "学到了", "哦原来如此", "非常感谢", "❤️", "👍"
    ]
    
    text_lower = text.lower()
    found = sum(1 for marker in positive_markers if marker.lower() in text_lower)
    
    return min(1.0, found * 0.2)


def _detect_correction(text: str) -> float:
    """检测用户是否在纠正 AI"""
    negative_markers = [
        "不对", "错了", "不是这样", "其实", "应该是", "你搞错了",
        "我纠正一下", "不准确", "有问题"
    ]
    
    text_lower = text.lower()
    found = sum(1 for marker in negative_markers if marker.lower() in text_lower)
    
    return min(1.0, found * 0.25)


async def update_profile_quality(
    session: AsyncSession,
    quality_score: float
):
    """用移动平均更新 AI 的质量评分"""
    profile = await get_ai_profile(session)
    
    # 移动平均：70% 旧值 + 30% 新值
    profile.response_quality_avg = (
        0.7 * profile.response_quality_avg +
        0.3 * quality_score
    )
    
    await session.commit()
    print(f"📊 更新回答质量评分: {profile.response_quality_avg:.2f}")


# ============================================================================
# 使用示例
# ============================================================================

"""
在应用启动时或定期任务中使用：

async def periodic_self_reflection():
    '''每日运行一次，反思过去 24 小时的对话'''
    session = get_session()
    
    # 获取最近 24 小时的对话
    cutoff = datetime.utcnow() - timedelta(hours=24)
    recent = await session.execute(
        select(Conversation)
        .where(Conversation.created_at > cutoff)
        .order_by(Conversation.created_at.desc())
        .limit(50)
    )
    
    conversations = recent.scalars().all()
    
    total_quality = 0
    for i, conv in enumerate(conversations[:-1]):
        next_conv = conversations[i + 1]
        
        quality = await evaluate_response_quality(
            conv.ai_response,
            next_conv.user_message,
            session
        )
        total_quality += quality
    
    if conversations:
        avg_quality = total_quality / len(conversations)
        await update_profile_quality(session, avg_quality)
        
        print(f"✨ 今日质量平均分: {avg_quality:.2f}")
"""


