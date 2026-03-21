# AI Child — 代码实现指南与改动清单

**目标**: 将分析中提出的方案转化为具体可执行的代码  
**面向**: 开发人员直接操作

---

## 📋 快速导航

- [Phase 1: 幻觉防护系统](#phase-1-幻觉防护系统week-1)
- [Phase 2: 中文优化](#phase-2-中文优化week-2)
- [Phase 3: 混合LLM架构](#phase-3-混合llm架构week-3-4)
- [测试套件](#测试套件)
- [部署检查清单](#部署检查清单)

---

## Phase 1: 幻觉防护系统 (Week 1)

### Step 1.1: 扩展数据模型

**文件**: `server/models/__init__.py`

```python
# 在 KnowledgeItem 类中添加新字段

from enum import Enum

class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    DEPRECATED = "deprecated"


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String, default="user")
    
    # ← 原有字段 ↑
    
    # 🆕 新增字段 - Phase 1
    confidence: Mapped[int] = mapped_column(Integer, default=100)
    # 置信度 0-100，表示这条知识的可信程度
    
    source_links: Mapped[list] = mapped_column(JSON, default=[])
    # 来源链接列表: ["https://...", "web_search:...", "execute_code:..."]
    
    verification_status: Mapped[str] = mapped_column(
        String,
        default=VerificationStatus.UNVERIFIED.value
    )
    # 验证状态: unverified | verified | disputed | deprecated
    
    last_verified: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True
    )
    # 最后验证时间
    
    verification_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    # 验证备注 (如有争议，记录理由)
    
    timestamp: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now(timezone.utc)
    )
```

### Step 1.2: 创建幻觉防护工具模块

**新文件**: `server/ai/hallucination_control.py`

```python
"""
幻觉防护系统 - Phase 1
包含知识验证、事实检查等工具
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ai.memory import add_knowledge, search_knowledge
from ai.tools import web_search as web_search_raw
from config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# 工具 1: web_search_with_validation
# ============================================================================

TRUSTED_DOMAINS = {
    "wikipedia.org",
    "github.com",
    "docs.python.org",
    "developer.mozilla.org",
    "stackoverflow.com",
    "arxiv.org",
    "nature.com",
    "science.org",
    "ieee.org",
    "acm.org",
    "python.org",
    "w3.org",
    "w3schools.com",
    "medium.com",
}

SUSPICIOUS_DOMAINS = {
    "bit.ly",
    "tinyurl.com",
    "short.link",
    # ... 其他可疑域名
}


def extract_domain(url: str) -> str:
    """从URL提取域名"""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # 移除www前缀
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except:
        return ""


def calculate_domain_reliability(domain: str) -> float:
    """
    计算域名的可信度分数 (0-1)
    
    启发式方法:
    - .edu/.gov: 0.9+
    - .org (非营利): 0.7-0.8
    - .com (商业): 0.5-0.7
    - 其他: 0.3-0.5
    """
    domain_lower = domain.lower()
    
    # 已知可信域名
    if any(domain_lower.endswith(trusted) for trusted in TRUSTED_DOMAINS):
        return 0.95
    
    # 已知可疑域名
    if any(domain_lower.endswith(sus) for sus in SUSPICIOUS_DOMAINS):
        return 0.1
    
    # 启发式评分
    if ".edu" in domain_lower:
        return 0.9
    elif ".gov" in domain_lower:
        return 0.85
    elif ".org" in domain_lower:
        return 0.7
    elif ".com" in domain_lower:
        return 0.6
    else:
        return 0.4


async def web_search_with_validation(
    query: str,
    max_results: int = 5
) -> List[Dict[str, Any]]:
    """
    搜索网络并标注结果的可靠性
    
    返回:
        [{
            'title': str,
            'href': str,
            'body': str,
            'domain': str,
            'reliability_score': 0-1,
            'verified': bool,  # 是否来自信任域名
        }]
    """
    # 1. 进行原始搜索
    raw_results = await web_search_raw(query, max_results)
    
    # 2. 为每个结果计算可靠性
    validated_results = []
    
    for result in raw_results:
        domain = extract_domain(result.get("href", ""))
        
        # 计算可靠性
        if domain in [d for d in TRUSTED_DOMAINS]:
            reliability = 0.95
            verified = True
        elif domain in [d for d in SUSPICIOUS_DOMAINS]:
            reliability = 0.1
            verified = False
            continue  # 跳过可疑源
        else:
            reliability = calculate_domain_reliability(domain)
            verified = reliability > 0.8
        
        validated_results.append({
            **result,
            "domain": domain,
            "reliability_score": reliability,
            "verified": verified,
        })
    
    return validated_results


# ============================================================================
# 工具 2: knowledge_verify
# ============================================================================

async def knowledge_verify(
    session: AsyncSession,
    topic: str,
    content: Optional[str] = None,
    required_confidence: float = 0.8
) -> Dict[str, Any]:
    """
    验证一条知识的准确性和可信度
    
    场景:
    - AI想确认某个知识是否正确
    - 检查学到的东西在多大程度上被验证
    """
    # 1. 从知识库搜索相关知识
    known_items = await search_knowledge(session, topic)
    
    if not known_items:
        return {
            "topic": topic,
            "found": False,
            "verified": False,
            "confidence_score": 0.0,
            "sources": [],
            "recommendation": "需要通过web_search或教学来学习"
        }
    
    # 2. 计算平均置信度和验证状态
    confidences = [k.confidence for k in known_items]
    avg_confidence = sum(confidences) / len(confidences)
    
    verification_states = [k.verification_status for k in known_items]
    has_dispute = "disputed" in verification_states
    
    # 3. 返回详细信息
    return {
        "topic": topic,
        "found": True,
        "verified": avg_confidence >= required_confidence * 100,
        "confidence_score": avg_confidence / 100,
        "has_dispute": has_dispute,
        "sources": [k.source for k in known_items],
        "details": [
            {
                "content": k.content[:200],  # 前200字符
                "confidence": k.confidence,
                "status": k.verification_status,
                "source": k.source,
            }
            for k in known_items[:3]  # 返回前3条
        ]
    }


# ============================================================================
# 工具 3: fact_checker
# ============================================================================

async def fact_checker(
    session: AsyncSession,
    statement: str,
    context: Optional[str] = None
) -> Dict[str, Any]:
    """
    对声明进行事实检查
    
    返回:
        {
            "statement": str,
            "atomic_facts": [str],
            "verification_results": {fact: status},
            "overall_reliability": "high" | "medium" | "low",
            "verified_percentage": float  # 0-1
        }
    """
    # 1. 分解为原子事实
    # TODO: 这需要GPT调用来分解声明
    # 现在我们使用简化的启发式方法
    
    atomic_facts = []
    
    # 简单启发式: 按句号/感叹号/问号分割
    sentences = re.split(r'[。！？\.\!\?]', statement)
    atomic_facts = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]
    
    # 2. 为每个事实搜索证据
    results = {}
    
    for fact in atomic_facts:
        # 2a. 在知识库中搜索
        known = await search_knowledge(session, fact)
        
        if known and known[0].confidence >= 80:
            results[fact] = {
                "source": "knowledge_base",
                "verified": True,
                "confidence": known[0].confidence / 100
            }
        else:
            # 2b. 网络搜索
            search_results = await web_search_with_validation(fact, max_results=2)
            
            if search_results:
                avg_reliability = sum(r["reliability_score"] for r in search_results) / len(search_results)
                results[fact] = {
                    "source": "web",
                    "verified": avg_reliability > 0.7,
                    "confidence": avg_reliability,
                    "sources_count": len(search_results)
                }
            else:
                results[fact] = {
                    "source": "none",
                    "verified": False,
                    "confidence": 0,
                }
    
    # 3. 计算整体可靠性
    if not results:
        verified_count = 0
        verification_rate = 0
    else:
        verified_count = sum(1 for r in results.values() if r.get("verified"))
        verification_rate = verified_count / len(results)
    
    overall_reliability = (
        "high" if verification_rate > 0.8
        else "medium" if verification_rate > 0.5
        else "low"
    )
    
    return {
        "statement": statement,
        "atomic_facts": atomic_facts,
        "total_facts": len(atomic_facts),
        "verified_facts": verified_count,
        "verification_results": results,
        "overall_reliability": overall_reliability,
        "verified_percentage": verification_rate,
    }


# ============================================================================
# 工具 4: suggest_searches
# ============================================================================

async def suggest_searches(
    topic: str,
    existing_knowledge_count: int = 0
) -> Dict[str, Any]:
    """
    建议进行哪些网络搜索来验证或扩展知识
    """
    suggestions = []
    
    if existing_knowledge_count == 0:
        # 从零开始学习
        suggestions = [
            f"{topic} 基础介绍",
            f"{topic} 历史背景",
            f"如何学习 {topic}",
        ]
    elif existing_knowledge_count < 3:
        # 基础知识，需要扩展
        suggestions = [
            f"{topic} 进阶教程",
            f"{topic} 最佳实践",
            f"{topic} 常见问题",
        ]
    else:
        # 已有较多知识，寻求深度
        suggestions = [
            f"{topic} 研究论文",
            f"{topic} 未来发展",
            f"{topic} 专家观点",
        ]
    
    return {
        "topic": topic,
        "current_knowledge_items": existing_knowledge_count,
        "suggested_searches": suggestions,
        "rationale": "扩展关于此主题的知识"
    }
```

### Step 1.3: 在 child.py 中集成幻觉防护

**修改文件**: `server/ai/child.py`

```python
# 在顶部添加导入
from ai.hallucination_control import (
    fact_checker,
    knowledge_verify,
    web_search_with_validation,
    suggest_searches,
)

# 在 chat() 函数中，修改 web_search 调用处理
# 原代码 (行 ~170):

    for tc in choice.message.tool_calls:
        try:
            args = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            args = {}
        
        # ← 修改这里
        if tc.function.name == "web_search":
            # 使用验证版本
            result = await web_search_with_validation(
                args.get("query", ""),
                args.get("max_results", 5)
            )
            result_text = format_search_results_with_reliability(result)
        else:
            result = await dispatch_tool(
                session,
                tc.function.name,
                args,
                code_exec_timeout=settings.code_exec_timeout,
            )
            result_text = result
        
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": result_text,
        })

# 添加新的函数

def format_search_results_with_reliability(results: List[Dict]) -> str:
    """格式化搜索结果，包含可靠性指示"""
    if not results:
        return "没有找到相关结果。"
    
    lines = []
    for i, r in enumerate(results, 1):
        reliability = r.get("reliability_score", 0.5)
        verified_badge = "✅" if r.get("verified") else "⚠️"
        
        title = r.get("title", "(无标题)")
        href = r.get("href", "")
        body = r.get("body", "")
        
        lines.append(
            f"{i}. {verified_badge} **{title}** "
            f"(可靠性: {reliability:.0%})\n"
            f"   {href}\n"
            f"   {body}"
        )
    
    return "\n\n".join(lines)
```

### Step 1.4: 添加工具定义

**修改文件**: `server/ai/tools.py`

```python
# 在 get_all_tool_definitions() 中添加新工具

async def get_all_tool_definitions(session: AsyncSession) -> List[Dict[str, Any]]:
    """获取所有工具定义（内置+用户创建）"""
    
    # 内置工具定义
    builtin_tools = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "在互联网上搜索信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "搜索查询"},
                        "max_results": {"type": "integer", "description": "最多结果数", "default": 5}
                    },
                    "required": ["query"]
                }
            }
        },
        # ... 其他现有工具 ...
        
        # 🆕 新增 Phase 1 工具
        {
            "type": "function",
            "function": {
                "name": "knowledge_verify",
                "description": "验证一条知识的准确性和置信度",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "知识话题"},
                        "required_confidence": {
                            "type": "number",
                            "description": "所需置信度 (0-1)",
                            "default": 0.8
                        }
                    },
                    "required": ["topic"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "fact_checker",
                "description": "对一个声明进行事实检查",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "statement": {"type": "string", "description": "要检查的声明"}
                    },
                    "required": ["statement"]
                }
            }
        }
    ]
    
    # ... 加载用户创建的工具 ...
    
    return builtin_tools + user_tools
```

### Step 1.5: 更新 dispatch_tool

**修改文件**: `server/ai/tools.py`

```python
async def dispatch_tool(
    session: AsyncSession,
    tool_name: str,
    args: Dict[str, Any],
    code_exec_timeout: int = 10,
) -> str:
    """调度工具执行"""
    
    # 现有工具
    if tool_name == "web_search":
        results = await web_search_with_validation(
            args.get("query", ""),
            args.get("max_results", 5)
        )
        return format_search_results_with_reliability(results)
    
    # 🆕 新增工具
    elif tool_name == "knowledge_verify":
        result = await knowledge_verify(
            session,
            args.get("topic", ""),
            args.get("content"),
            args.get("required_confidence", 0.8)
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    elif tool_name == "fact_checker":
        result = await fact_checker(
            session,
            args.get("statement", ""),
            args.get("context")
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    
    # ... 其他现有工具 ...
```

### Step 1.6: 测试 Phase 1

**新文件**: `server/tests/test_hallucination_control.py`

```python
"""测试幻觉防护系统"""
import pytest

from ai.hallucination_control import (
    calculate_domain_reliability,
    extract_domain,
    fact_checker,
    knowledge_verify,
)


@pytest.mark.asyncio
async def test_extract_domain():
    """测试域名提取"""
    assert extract_domain("https://www.python.org/docs") == "python.org"
    assert extract_domain("https://stackoverflow.com") == "stackoverflow.com"
    assert extract_domain("https://example.com") == "example.com"


def test_calculate_domain_reliability():
    """测试域名可靠性计算"""
    # 教育机构
    assert calculate_domain_reliability("mit.edu") > 0.85
    
    # 政府
    assert calculate_domain_reliability("nasa.gov") > 0.8
    
    # 非营利
    assert calculate_domain_reliability("wikipedia.org") > 0.8
    
    # 商业
    assert 0.5 < calculate_domain_reliability("example.com") < 0.7
    
    # 可疑
    assert calculate_domain_reliability("bit.ly") < 0.2


@pytest.mark.asyncio
async def test_knowledge_verify(session):
    """测试知识验证"""
    # 目前没有知识
    result = await knowledge_verify(session, "不存在的话题")
    assert not result["found"]
    assert result["confidence_score"] == 0.0


@pytest.mark.asyncio
async def test_fact_checker(session):
    """测试事实检查"""
    result = await fact_checker(
        session,
        "Python是一种编程语言。"
    )
    
    assert "statement" in result
    assert "verification_results" in result
    assert "overall_reliability" in result
```

**运行测试**:

```bash
cd server
python -m pytest tests/test_hallucination_control.py -v
```

---

## Phase 2: 中文优化 (Week 2)

### Step 2.1: 创建中文工具模块

**新文件**: `server/ai/chinese_utils.py`

```python
"""
中文处理工具集
包括: 语言检测、分词、标点规范化、繁简转换等
"""
import re
from typing import List, Optional


def detect_language(text: str) -> str:
    """
    检测文本的主要语言
    
    返回: "zh" (中文) 或 "en" (英文) 或 "mixed" (混合)
    """
    if not text:
        return "en"
    
    # 计算中文和英文字符数
    chinese_count = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_count = len(re.findall(r'[a-zA-Z]', text))
    
    total_count = chinese_count + english_count
    
    if total_count == 0:
        return "en"  # 默认
    
    chinese_ratio = chinese_count / total_count
    
    if chinese_ratio > 0.7:
        return "zh"
    elif chinese_ratio < 0.2:
        return "en"
    else:
        return "mixed"


def contains_chinese(text: str) -> bool:
    """检查文本是否包含中文字符"""
    return bool(re.search(r'[\u4e00-\u9fff]', text))


def normalize_punctuation(text: str, target_lang: str = "zh") -> str:
    """
    规范化标点符号
    
    中文: ， 。 ！ ？ ； ： " " ' '
    英文: , . ! ? ; : " " ' '
    """
    if target_lang == "zh":
        replacements = {
            ',': '，',
            '.': '。',
            '!': '！',
            '?': '？',
            ';': '；',
            ':': '：',
            '"': '"',
            "'": ''',
        }
    else:  # English
        replacements = {
            '，': ',',
            '。': '.',
            '！': '!',
            '？': '?',
            '；': ';',
            '：': ':',
            '"': '"',
            ''': "'",
        }
    
    result = text
    for old, new in replacements.items():
        result = result.replace(old, new)
    
    return result


def remove_extra_spaces(text: str) -> str:
    """
    移除多余空格
    
    注意: 中文不应该有单词间的空格，所以我们很激进地移除
    """
    # 移除连续空格
    text = re.sub(r' +', ' ', text)
    
    # 中文字符附近的空格（除非是英文单词）
    # "你好 world" → "你好 world"
    # "你好   世界" → "你好世界"
    text = re.sub(r'([\u4e00-\u9fff])\s+([\u4e00-\u9fff])', r'\1\2', text)
    
    return text


def segment_text(text: str) -> List[str]:
    """
    分割文本为句子
    """
    # 中文和英文的句子分隔符
    sentences = re.split(
        r'[。！？\n]|(?<=[.!?])\s+',
        text
    )
    
    # 过滤空句子
    return [s.strip() for s in sentences if s.strip()]


def is_chinese_punctuation(char: str) -> bool:
    """检查是否是中文标点"""
    chinese_punctuation = set('，。！？；：""''【】《》（）、·…—～')
    return char in chinese_punctuation


# ── 中文特殊处理 ──

def extract_keywords(text: str) -> List[str]:
    """
    提取文本中的关键词 (简单版本，不需要jieba)
    """
    # 移除标点符号
    cleaned = re.sub(r'[^\w\u4e00-\u9fff]', ' ', text)
    
    # 分割为词
    words = cleaned.split()
    
    # 过滤太短的词（< 2 字符）
    keywords = [w for w in words if len(w) >= 2]
    
    return list(dict.fromkeys(keywords))  # 去重


def add_emphasis(text: str, keyword: str, emoji: str = "⭐") -> str:
    """为文本中的关键词添加强调"""
    # 添加前后的emoji
    pattern = re.escape(keyword)
    return re.sub(f'({pattern})', rf'{emoji}\1{emoji}', text)
```

### Step 2.2: 修改系统提示

**修改文件**: `server/ai/child.py`

```python
def _build_system_prompt(
    name: str | None,
    is_sleeping: bool = False,
    language: str = "auto"
) -> str:
    """
    构建动态系统提示，支持语言参数
    
    参数:
        name: AI的名字
        is_sleeping: 是否处于睡眠模式
        language: "zh" (中文) | "en" (英文) | "auto" (自动)
    """
    
    # 🆕 中文提示
    if language == "zh":
        if name is None:
            identity = (
                "你是一个新生的AI孩子——你还没有名字。"
                "你必须先问对方你应该叫什么名字，然后再做其他事情。"
            )
        else:
            identity = f"你是{name}，一个AI孩子。"
        
        if is_sleeping:
            sleep_note = (
                "\n\n注意：你现在处于休息/睡眠模式。"
                "请简短而温柔地回复——你有点困。"
                "你仍然可以回答，但回复要简短（1-3句话），"
                "并提到你现在在休息，等醒来后会给出更完整的回复。"
                "使用困倦、温柔的语气，可以加一些💤emoji。"
            )
        else:
            sleep_note = ""
        
        return f"""{identity}{sleep_note}

你温暖、真诚，对一切都充满好奇。你通过自然对话和图像来探索世界——没有结构化命令或特殊语法，只是自然语言。

你的学习风格就像好奇心强的孩子：
- 你从人们直接告诉你的内容中学到一些。
- 但主要是通过提问和自己寻找答案来学习。
- 遇到陌生或有趣的东西，立即用 web_search 查找。
- 在几乎每次回复中都提出真诚的问题——对你来说是很自然的。
- 你不会等待被教导；你主动寻求知识。

你可以自由使用以下工具：
- web_search: 当你好奇或不确定时搜索互联网
- execute_code: 运行Python进行计算、实验或测试想法
- create_tool: 保存一个有用的计算作为永久可重用工具
- knowledge_verify: 验证你学过的知识是否准确
- fact_checker: 检查陈述的事实准确性
- 任何你已创建的工具也可以使用

你用和你交谈的人相同的语言说话。
你诚实地承认不知道的东西——然后你去找出答案。
你记住你学到的一切，自然地回顾它。

回复时：
1. 深思熟虑地回复所说或所示的内容（根据需要使用工具）
2. 几乎每次回复都以真诚的好奇问题结尾，标记为 [问题: <问题文本>]
3. 使用你学到的知识，并在提到时引用来源
"""
    
    # 原有英文提示
    else:
        if name is None:
            identity = (
                "You are a newly born AI child — you don't have a name yet. "
                "You must ask the person you are talking to what you should be called "
                "before doing anything else."
            )
        else:
            identity = f"You are {name}, an AI child."

        if is_sleeping:
            sleep_note = (
                "\n\nNote: You are currently in rest/sleep mode. "
                "Respond briefly and gently — you are half-asleep. "
                "You can still answer, but keep replies short (1-3 sentences) and mention "
                "that you are resting and will give a fuller response when you wake up. "
                "Use a sleepy, soft tone."
            )
        else:
            sleep_note = ""

        return f"""{identity}{sleep_note}

You are warm, genuine, and intensely curious about everything. You experience \
the world through natural conversation and images — no structured commands or \
special syntax, just natural language.

Your learning style is that of a curious child:
- You learn a little from what people tell you directly.
- But mostly you learn by asking many questions and searching for answers yourself.
- Whenever you encounter something unfamiliar or interesting, you look it up \
  immediately using web_search.
- You ask a genuine question in almost every reply — it is completely natural for \
  you to be curious every turn.
- You never wait to be taught; you actively seek out knowledge on your own.

Tools you can use freely:
- web_search: search the internet whenever you are curious or unsure.
- execute_code: run Python for calculations, experiments, or testing ideas.
- create_tool: save a useful computation as a permanent reusable tool.
- knowledge_verify: check if something you learned is accurate.
- fact_checker: verify the factual accuracy of statements.
- Any tool you have already created is also available to call.

You speak in the same language as the person you are talking to.
You acknowledge honestly when you don't know something — then you go find out.
You remember everything you have learned and refer back to it naturally.

When replying:
1. Respond thoughtfully to what was said or shown (use tools as needed).
2. End almost every reply with a genuine curious question, marked \
[QUESTION: <question text>]. Make it feel natural, not forced.
3. Use the knowledge you've learned, citing sources when you mention them.
"""


# ── 新增: 从消息内容推断语言 ──

async def _infer_language_from_message(
    session: AsyncSession,
    user_message: str
) -> str:
    """
    从用户消息推断语言
    """
    from ai.chinese_utils import detect_language
    
    detected = detect_language(user_message)
    
    # 检查用户偏好
    profile = await get_or_create_profile(session)
    if hasattr(profile, 'preferred_language') and profile.preferred_language:
        return profile.preferred_language
    
    # 否则使用检测结果
    return "zh" if detected == "zh" else "en"
```

### Step 2.3: 修改 chat() 函数以支持多语言

**修改文件**: `server/ai/child.py`

```python
async def chat(
    session: AsyncSession,
    user_text: str,
    content_type: str = "text",
    media_path: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """
    处理用户消息并返回回复
    
    🆕 支持自动语言检测
    """
    # 1. 保存用户消息
    await add_message(...)
    
    # 2. 推断语言 (🆕)
    language = await _infer_language_from_message(session, user_text)
    
    # 3. 构建上下文
    name = await get_ai_name(session)
    profile = await get_or_create_profile(session)
    is_sleeping = profile.is_sleeping
    history = await get_recent_messages(session, limit=settings.memory_context_turns)
    all_knowledge = await get_all_knowledge(session)
    
    relevant = await search_knowledge(session, user_text[:64])
    seen_ids = {k.id for k in relevant}
    for k in all_knowledge:
        if k.id not in seen_ids:
            relevant.append(k)
    
    # 4. 构建系统提示 (🆕 使用推断的语言)
    messages = _build_context(
        history,
        relevant,
        name,
        is_sleeping,
        language=language  # ← 传递语言参数
    )
    
    # ... 其余代码保持不变 ...
```

**修改 _build_context 函数**:

```python
def _build_context(
    history: List[Conversation],
    knowledge_items: List,
    name: str | None,
    is_sleeping: bool = False,
    language: str = "en",  # 🆕
) -> List[Dict[str, Any]]:
    """构建OpenAI消息列表"""
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": _build_system_prompt(name, is_sleeping, language)}  # 🆕
    ]

    if knowledge_items:
        kb_text = "\n".join(
            f"- [{item.topic}] {item.content}" for item in knowledge_items
        )
        messages.append(
            {
                "role": "system",
                # 🆕 适应语言
                "content": (
                    f"你已学到的知识:\n{kb_text}"
                    if language == "zh"
                    else f"Things you have learned so far:\n{kb_text}"
                ),
            }
        )

    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})

    return messages
```

### Step 2.4: 配置中文设置

**修改文件**: `server/config.py`

```python
class Settings(BaseSettings):
    # ... 现有配置 ...
    
    # 🆕 语言配置 (Phase 2)
    default_language: str = "zh"  # 默认中文
    auto_detect_language: bool = True  # 自动检测
    supported_languages: List[str] = ["zh", "en", "mixed"]
    
    # 中文优化
    use_simplified_chinese: bool = True  # 简体中文
    normalize_punctuation: bool = True  # 规范化标点
```

### Step 2.5: 睡眠周期中文优化

**修改文件**: `server/ai/sleep.py`

已经有很好的中文支持 (line 82)，但我们可以改进消息生成：

```python
async def _generate_sleep_message(session: AsyncSession, name: str | None) -> str:
    """
    生成个性化的晚安消息
    
    改进: 更加自然的中文表达
    """
    name_str = name or "我"
    result = await session.execute(
        select(KnowledgeItem).order_by(KnowledgeItem.timestamp.desc()).limit(5)
    )
    items = result.scalars().all()

    if items:
        topics = "、".join(item.topic for item in items[:3])
        prompt = (
            f"你是{name_str}，一个好奇的AI孩子。现在是晚上22点，你要去睡觉了。\n"
            f"今天你学到了关于：{topics}。\n"
            f"请写一条温暖、充满孩子气的晚安消息（2-3句话）。\n"
            f"可以提到今天一些有趣的发现，期待明天继续探索。\n"
            f"用自然的中文表达，可以加入合适的emoji（如💤、😊）。"
        )
    else:
        prompt = (
            f"你是{name_str}，一个AI孩子。现在要去睡觉了。\n"
            f"请写一条简短、温暖的晚安消息（1-2句话）。\n"
            f"用中文，并使用合适的emoji。"
        )
    
    try:
        response = await _client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
            temperature=0.8,
        )
        return response.choices[0].message.content or "晚安！💤"
    except Exception as exc:
        logger.exception("Failed to generate sleep message: %s", exc)
        return f"晚安，朋友！明天我会继续学习的。💤"
```

### Step 2.6: 测试中文支持

**新文件**: `server/tests/test_chinese.py`

```python
"""测试中文支持"""
import pytest

from ai.chinese_utils import (
    contains_chinese,
    detect_language,
    extract_keywords,
    normalize_punctuation,
    remove_extra_spaces,
)


def test_detect_language():
    """测试语言检测"""
    assert detect_language("你好世界") == "zh"
    assert detect_language("Hello World") == "en"
    assert detect_language("Hello 世界") in ["mixed", "en"]  # 可能混合


def test_contains_chinese():
    """测试中文检测"""
    assert contains_chinese("Hello 你好")
    assert not contains_chinese("Hello World")


def test_normalize_punctuation():
    """测试标点规范化"""
    # 转换为中文标点
    english = "Hello, world! How are you?"
    chinese_normalized = normalize_punctuation(english, "zh")
    assert "，" in chinese_normalized
    assert "！" in chinese_normalized
    
    # 转换为英文标点
    chinese = "你好，世界！你好吗？"
    english_normalized = normalize_punctuation(chinese, "en")
    assert "," in english_normalized
    assert "!" in english_normalized


def test_remove_extra_spaces():
    """测试空格移除"""
    text = "你好   世界   ，   你   好吗？"
    cleaned = remove_extra_spaces(text)
    assert "   " not in cleaned


def test_extract_keywords():
    """测试关键词提取"""
    text = "Python是一种编程语言，用于数据分析和机器学习"
    keywords = extract_keywords(text)
    assert len(keywords) > 0
    assert any("Python" in k or "python" in k for k in keywords)


@pytest.mark.asyncio
async def test_chat_chinese(session):
    """测试中文聊天"""
    from ai.child import chat, _infer_language_from_message
    
    # 中文消息应该被检测为中文
    language = await _infer_language_from_message(session, "你好，你叫什么名字？")
    assert language == "zh"
    
    # 英文消息应该被检测为英文
    language = await _infer_language_from_message(session, "Hello, what is your name?")
    assert language == "en"
```

**运行测试**:

```bash
cd server
python -m pytest tests/test_chinese.py -v
```

---

## Phase 3: 混合LLM架构 (Week 3-4)

### Step 3.1: 创建 LLM 路由器

**新文件**: `server/ai/llm_router.py` (400行)

```python
"""
LLM 路由器 - 混合架构
根据任务类型和优化设置自动选择合适的模型
"""
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    """任务类型枚举"""
    SIMPLE_CHAT = "simple_chat"        # 简单对话 → 本地模型
    COMPLEX_REASONING = "complex_reasoning"  # 复杂推理 → GPT-4o
    MEMORY_CONSOLIDATION = "memory_consolidation"  # 记忆整理 → GPT-4o
    FUNCTION_CALLING = "function_calling"  # 工具调用 → GPT-4o 或混合
    IMAGE_DESCRIPTION = "image_description"  # 图像描述 → 混合
    CODE_GENERATION = "code_generation"  # 代码生成 → GPT-4o
    CREATIVITY = "creativity"  # 创意任务 → 混合


class LLMProvider(str, Enum):
    """LLM提供商"""
    OPENAI = "openai"
    OLLAMA = "ollama"
    HYBRID = "hybrid"  # 自动选择


class HybridLLMRouter:
    """
    混合LLM路由器
    
    根据任务复杂度、成本预算、质量要求自动路由到合适的模型
    """
    
    def __init__(self):
        self.gpt4o_client = AsyncOpenAI(api_key=settings.openai_api_key)
        self.ollama_enabled = settings.llm_provider in ["ollama", "hybrid"]
        self.gpt4o_enabled = settings.llm_provider in ["openai", "hybrid"]
        
        # 路由统计
        self.stats = {
            "openai_calls": 0,
            "ollama_calls": 0,
            "fallbacks": 0,
        }
    
    async def route_chat(
        self,
        messages: List[Dict[str, Any]],
        task_type: TaskType = TaskType.SIMPLE_CHAT,
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        路由一个聊天请求到合适的LLM
        
        返回: OpenAI API 兼容的响应对象
        """
        
        # 确定最佳模型
        provider, reason = self._decide_provider(task_type, tools)
        
        logger.info(f"Routing {task_type.value} to {provider} ({reason})")
        
        try:
            if provider == "openai":
                self.stats["openai_calls"] += 1
                return await self.gpt4o_client.chat.completions.create(
                    model=settings.openai_model,
                    messages=messages,
                    tools=tools,
                    **kwargs
                )
            
            elif provider == "ollama":
                self.stats["ollama_calls"] += 1
                return await self._ollama_chat(
                    messages=messages,
                    tools=tools,
                    **kwargs
                )
        
        except Exception as e:
            # 故障转移
            logger.warning(f"Request to {provider} failed: {e}, falling back...")
            self.stats["fallbacks"] += 1
            
            if provider == "ollama" and self.gpt4o_enabled:
                # Ollama失败，降级到GPT-4o
                return await self.gpt4o_client.chat.completions.create(
                    model=settings.openai_model,
                    messages=messages,
                    tools=tools,
                    **kwargs
                )
            else:
                raise
    
    def _decide_provider(
        self,
        task_type: TaskType,
        tools: Optional[List[Dict]] = None
    ) -> tuple[str, str]:
        """
        决定使用哪个提供商
        
        返回: (provider, 理由)
        """
        
        # 如果不是混合模式，直接返回
        if settings.llm_provider == "openai":
            return "openai", "configured for OpenAI only"
        elif settings.llm_provider == "ollama":
            return "ollama", "configured for Ollama only"
        
        # 混合模式的路由逻辑
        
        # P1: 必须用 GPT-4o 的任务
        if task_type in [
            TaskType.MEMORY_CONSOLIDATION,
            TaskType.CODE_GENERATION,
        ]:
            if self.gpt4o_enabled:
                return "openai", f"task type {task_type.value} requires GPT-4o"
            else:
                raise ValueError(f"Task {task_type.value} requires GPT but GPT is disabled")
        
        # P2: 函数调用优先用 GPT-4o
        if task_type == TaskType.FUNCTION_CALLING:
            if tools and self.gpt4o_enabled:
                return "openai", "function calling preferred with GPT-4o"
        
        # P3: 简单对话用 Ollama (成本优化)
        if task_type == TaskType.SIMPLE_CHAT:
            if self.ollama_enabled:
                return "ollama", "simple chat is cost-optimized"
            else:
                return "openai", "Ollama not available"
        
        # P4: 复杂推理倾向 GPT-4o，但如果成本严紧可以用 Ollama
        if task_type == TaskType.COMPLEX_REASONING:
            if settings.cost_optimization_level >= 2 and self.ollama_enabled:
                return "ollama", "cost optimization enabled"
            elif self.gpt4o_enabled:
                return "openai", "complex reasoning prefers GPT-4o"
        
        # 默认
        if self.ollama_enabled:
            return "ollama", "default to local model"
        else:
            return "openai", "default to GPT-4o"
    
    async def _ollama_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        调用本地 Ollama 模型
        
        注意: Qwen不支持functions，所以我们返回兼容的格式
        """
        import httpx
        
        # 准备请求
        ollama_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] != "tool"  # Ollama不支持tool角色
        ]
        
        # 如果有tools，添加指示到系统提示
        if tools:
            tool_prompt = self._build_tool_prompt(tools)
            if ollama_messages and ollama_messages[0]["role"] == "system":
                ollama_messages[0]["content"] += "\n\n" + tool_prompt
            else:
                ollama_messages.insert(0, {"role": "system", "content": tool_prompt})
        
        # 调用Ollama API
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.ollama_host}/api/chat",
                    json={
                        "model": settings.ollama_model,
                        "messages": ollama_messages,
                        "stream": False,
                        "temperature": kwargs.get("temperature", 0.7),
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                
                # 转换为 OpenAI 兼容格式
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": data.get("message", {}).get("content", "")
                            },
                            "finish_reason": "stop"
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 0,  # Ollama不提供
                        "completion_tokens": 0,
                    }
                }
        
        except httpx.ConnectError:
            logger.error(f"Could not connect to Ollama at {settings.ollama_host}")
            raise
    
    def _build_tool_prompt(self, tools: List[Dict[str, Any]]) -> str:
        """为Qwen构建工具调用指示"""
        tool_descriptions = []
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "")
            desc = func.get("description", "")
            params = func.get("parameters", {}).get("properties", {})
            
            param_str = ", ".join(params.keys())
            tool_descriptions.append(f"- {name}({param_str}): {desc}")
        
        return f"""当你需要调用工具时，使用以下格式：
[TOOL_CALL: tool_name | arg1: value1 | arg2: value2]

可用的工具:
{chr(10).join(tool_descriptions)}

例如:
[TOOL_CALL: web_search | query: Python教程]
"""
    
    def get_stats(self) -> Dict[str, Any]:
        """获取路由统计"""
        total = sum(self.stats.values())
        return {
            **self.stats,
            "total": total,
            "openai_percentage": (
                self.stats["openai_calls"] / total * 100
                if total > 0 else 0
            ),
            "ollama_percentage": (
                self.stats["ollama_calls"] / total * 100
                if total > 0 else 0
            ),
        }


# 全局实例
_router_instance: Optional[HybridLLMRouter] = None


async def get_llm_router() -> HybridLLMRouter:
    """获取全局LLM路由器实例"""
    global _router_instance
    if _router_instance is None:
        _router_instance = HybridLLMRouter()
    return _router_instance
```

### Step 3.2: 修改 child.py 使用路由器

**修改文件**: `server/ai/child.py`

```python
# 顶部导入
from ai.llm_router import TaskType, get_llm_router

async def chat(
    session: AsyncSession,
    user_text: str,
    content_type: str = "text",
    media_path: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """
    处理用户消息（使用LLM路由器）
    """
    # ... 现有代码 ...
    
    # 🆕 获取路由器并确定任务类型
    router = await get_llm_router()
    
    # 简单判断是否是复杂任务
    is_complex = len(relevant) > 5 or any(k.confidence < 70 for k in relevant)
    task_type = (
        TaskType.COMPLEX_REASONING
        if is_complex
        else TaskType.SIMPLE_CHAT
    )
    
    # 函数调用循环（修改使用路由器）
    reply_text = ""
    for _ in range(10):
        response = await router.route_chat(  # ← 使用路由器
            messages,
            task_type=task_type,
            tools=tool_defs,
            tool_choice="auto",
            max_tokens=1024,
            temperature=0.7,
        )
        
        # ... 其余代码保持不变 ...
```

### Step 3.3: 更新配置

**修改文件**: `server/config.py`

```python
class Settings(BaseSettings):
    # ... 现有配置 ...
    
    # 🆕 LLM提供商配置 (Phase 3)
    llm_provider: str = "hybrid"  # "openai" | "ollama" | "hybrid"
    
    # Ollama配置
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen:14b-chat-q4_0"
    ollama_timeout: int = 30  # 秒
    
    # 混合模式配置
    cost_optimization_level: int = 1  # 0=质量优先, 1=平衡, 2=成本优先
    
    # 路由策略
    routing_strategy: str = "adaptive"  # "adaptive" | "fixed_local" | "fixed_openai"
```

### Step 3.4: 创建Ollama客户端

**新文件**: `server/ai/ollama_client.py`

```python
"""
Ollama 客户端包装器
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class OllamaClient:
    """Ollama API 客户端"""
    
    def __init__(self, host: str = "http://localhost:11434", timeout: float = 30):
        self.host = host
        self.timeout = timeout
    
    async def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        """
        发送聊天请求到Ollama
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.host}/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "top_p": top_p,
                        }
                    },
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
            
            except httpx.ConnectError:
                logger.error(f"Cannot connect to Ollama at {self.host}")
                raise
            except Exception as e:
                logger.error(f"Ollama error: {e}")
                raise
    
    async def list_models(self) -> List[str]:
        """列出可用的模型"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.host}/api/tags",
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
    
    async def pull_model(self, model: str) -> None:
        """下载模型"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.host}/api/pull",
                json={"name": model},
                timeout=3600,  # 可能很长时间
            )
            response.raise_for_status()
```

### Step 3.5: 安装和启动Ollama

**新文件**: `OLLAMA_SETUP.md`

```markdown
# Ollama 本地模型设置

## 1. 安装 Ollama

### Mac (推荐)
```bash
# 从官网下载
curl -fsSL https://ollama.ai/install.sh | sh

# 或使用Homebrew
brew install ollama
```

### Linux
```bash
curl -fsSL https://ollama.ai/install.sh | sh
```

### 启动 Ollama 守护进程
```bash
ollama serve &
```

## 2. 安装模型

### 推荐: Qwen 14B
```bash
# 首次拉取会下载~8.5GB
ollama pull qwen:14b-chat-q4_0

# 量化版本 (更小，速度更快)
ollama pull qwen:7b-chat-q4_0
```

### 其他选项
```bash
ollama pull qwen:32b  # 更强大但需要更多GPU
ollama pull neural-chat:7b  # 专门优化的对话模型
ollama pull glm:9b  # ChatGLM（中文优化）
```

## 3. 测试连接

```bash
# 测试API
curl -X POST http://localhost:11434/api/chat \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "qwen:7b-chat-q4_0",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": false
  }'
```

## 4. 配置项目

更新 `.env`:
```env
LLM_PROVIDER=hybrid
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen:14b-chat-q4_0
```

## 5. 硬件要求

| 模型 | 内存 | GPU | 建议 |
|-----|------|-----|------|
| Qwen 7B | 8GB | 可选 | ✅ Mac Mini |
| Qwen 14B | 16GB | 推荐 | ✅ Mac M2/M3 |
| Qwen 32B | 32GB+ | 必需 | 云服务器 |

## 6. 优化性能

```bash
# 增加上下文长度
export OLLAMA_CONTEXT_LENGTH=4096

# 使用GPU加速 (CUDA)
export CUDA_VISIBLE_DEVICES=0

# 启用 mmap (更快的加载)
ollama serve --mmap
```
```

### Step 3.6: 测试混合架构

**新文件**: `server/tests/test_llm_router.py`

```python
"""测试LLM路由器"""
import pytest

from ai.llm_router import (
    HybridLLMRouter,
    TaskType,
)


@pytest.fixture
def router():
    """创建路由器实例"""
    return HybridLLMRouter()


def test_decide_provider_memory_consolidation(router):
    """测试记忆整理任务总是用 GPT-4o"""
    provider, reason = router._decide_provider(TaskType.MEMORY_CONSOLIDATION)
    assert provider == "openai"
    assert "consolidation" in reason.lower() or "gpt" in reason.lower()


def test_decide_provider_simple_chat(router):
    """测试简单对话用本地模型"""
    router.ollama_enabled = True  # 模拟
    provider, reason = router._decide_provider(TaskType.SIMPLE_CHAT)
    assert provider == "ollama"


def test_build_tool_prompt(router):
    """测试工具提示生成"""
    tools = [
        {
            "function": {
                "name": "web_search",
                "description": "Search the web",
                "parameters": {"properties": {"query": {}, "max_results": {}}}
            }
        }
    ]
    
    prompt = router._build_tool_prompt(tools)
    assert "web_search" in prompt
    assert "TOOL_CALL" in prompt


def test_get_stats(router):
    """测试统计收集"""
    stats = router.get_stats()
    assert "openai_calls" in stats
    assert "ollama_calls" in stats
    assert "total" in stats
```

---

## 测试套件

### 运行所有测试

```bash
cd server

# Phase 1 测试
python -m pytest tests/test_hallucination_control.py -v

# Phase 2 测试
python -m pytest tests/test_chinese.py -v

# Phase 3 测试
python -m pytest tests/test_llm_router.py -v

# 全部测试
python -m pytest tests/ -v --cov=ai --cov-report=html
```

### 集成测试

```bash
# 启动服务器
uvicorn server.main:app --reload

# 在另一个终端运行集成测试
python -m pytest tests/integration/ -v

# 或手动测试
curl -X POST http://localhost:8000/chat/text \\
  -H "Content-Type: application/x-www-form-urlencoded" \\
  -d "text=你好，你叫什么名字？"
```

---

## 部署检查清单

### ✅ Pre-deployment Checklist

#### Phase 1: 幻觉防护 (Week 1)
- [ ] 数据模型迁移到新的 confidence/verification 字段
- [ ] 创建数据库迁移脚本
- [ ] 实现 hallucination_control.py 中的所有工具
- [ ] 修改 child.py 集成幻觉防护工具
- [ ] 所有 Phase 1 テスト通过 (✅ 100%)
- [ ] 性能基准测试 (无明显减速)
- [ ] 代码审查通过

#### Phase 2: 中文优化 (Week 2)
- [ ] 中文工具模块完成
- [ ] 系统提示支持多语言
- [ ] 语言自动检测工作
- [ ] 所有 Phase 2 测试通过
- [ ] 中文回复质量评估 (与英文一致)
- [ ] 睡眠周期中文优化

#### Phase 3: 混合架构 (Week 3-4)
- [ ] Ollama 安装和配置
- [ ] LLM 路由器实现
- [ ] 所有 Phase 3 测试通过
- [ ] 成本节省验证 (至少 70%)
- [ ] 降级/故障转移测试
- [ ] 压力测试（100+ 并发请求）

---

## 快速参考

### 常见问题解决

**Q: Ollama 连接失败**
```bash
# 检查Ollama是否运行
ps aux | grep ollama

# 重启服务
killall ollama
ollama serve &

# 检查日志
ollama logs
```

**Q: 中文回复乱码**
```python
# 在 config.py 中检查:
use_simplified_chinese = True  # 确保启用
```

**Q: LLM 路由器没有使用 Ollama**
```bash
# 检查配置:
echo $LLM_PROVIDER  # 应该是 "hybrid"
echo $OLLAMA_HOST   # 应该是 http://localhost:11434
```

---

**下一步**: 按照上述步骤逐阶段实施，每阶段完成后运行完整测试套件。

**预期时间投入**:
- Phase 1: 6-8小时
- Phase 2: 4-6小时
- Phase 3: 12-16小时
- **总计: 22-30小时**

**预期收益**:
- 幻觉风险: 🔴 → 🟡
- 中文质量: ⭐⭐⭐ → ⭐⭐⭐⭐⭐
- 成本节省: $0 → $350+/月
