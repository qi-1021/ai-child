"""
Tool registry and built-in tools for the AI Child.

Built-in tools (always available via OpenAI function calling):
  web_search(query, max_results)             – search DuckDuckGo
  execute_code(code, description)            – run Python in a subprocess sandbox
  create_tool(name, desc, code, params)      – define a new reusable tool stored in DB

Created tools are persisted in the `tools` table and loaded dynamically.
Each conversation offers the AI both built-ins and all previously created tools.
"""
import ast
import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional

from duckduckgo_search import DDGS
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Tool

logger = logging.getLogger(__name__)

# 防幻觉工具缓存（避免重复查询）
_knowledge_cache: Dict[str, tuple] = {}
_confidence_cache: Dict[str, float] = {}

# Maximum combined stdout+stderr captured from a sandboxed subprocess
_MAX_OUTPUT_BYTES = 8 * 1024  # 8 KB

# Modules the sandboxed code may NOT import
_BLOCKED_MODULES = frozenset({
    "os", "sys", "subprocess", "socket", "shutil", "pathlib",
    "importlib", "ctypes", "multiprocessing", "threading",
    "signal", "resource", "pty", "tty", "fcntl", "termios",
    "requests", "httpx", "urllib", "http", "ftplib", "smtplib",
    "telnetlib", "xmlrpc", "wsgiref", "antigravity",
})

# Built-in functions that must not be called in sandboxed code
_BLOCKED_BUILTINS = frozenset({
    "exec", "eval", "compile", "__import__", "breakpoint", "open", "input",
})

# Dunder attributes used in class-escape exploits
_BLOCKED_ATTRS = frozenset({
    "__class__", "__bases__", "__mro__", "__subclasses__",
    "__globals__", "__builtins__", "__code__", "__closure__", "__import__",
})


# ── Safety checker ────────────────────────────────────────────────────────────

def _check_code_safety(code: str) -> None:
    """
    Parse code as an AST and raise ValueError on dangerous constructs.

    This is a best-effort static check; subprocess isolation is the
    primary security boundary.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f"Syntax error: {exc}") from exc

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split(".")[0]
                if mod in _BLOCKED_MODULES:
                    raise ValueError(f"Import of '{mod}' is not allowed in sandbox.")

        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod in _BLOCKED_MODULES:
                raise ValueError(f"Import of '{mod}' is not allowed in sandbox.")

        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_BUILTINS:
                raise ValueError(f"Call to '{node.func.id}' is not allowed.")

        elif isinstance(node, ast.Attribute):
            if node.attr in _BLOCKED_ATTRS:
                raise ValueError(f"Access to '{node.attr}' is not allowed.")


# ── Web search ────────────────────────────────────────────────────────────────

def _sync_search(query: str, max_results: int) -> List[Dict[str, str]]:
    """Synchronous DuckDuckGo search (intended to run in a thread pool)."""
    with DDGS() as ddgs:
        return list(ddgs.text(query, max_results=max_results))


async def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Search DuckDuckGo and return a list of result dicts (title, href, body)."""
    max_results = max(1, min(max_results, 10))
    try:
        return await asyncio.to_thread(_sync_search, query, max_results)
    except Exception as exc:
        logger.warning("DuckDuckGo search failed for '%s': %s", query, exc)
        return []


def format_search_results(results: List[Dict[str, str]]) -> str:
    """Format search result dicts into a readable numbered list."""
    if not results:
        return "No results found."
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "(no title)")
        href = r.get("href", "")
        body = r.get("body", "")
        lines.append(f"{i}. **{title}**\n   {href}\n   {body}")
    return "\n\n".join(lines)


# ── Code sandbox ──────────────────────────────────────────────────────────────

async def execute_code_sandboxed(code: str, timeout: int = 10) -> str:
    """
    Execute Python code in an isolated subprocess and return its output.

    Safety layers:
      1. AST check rejects dangerous imports and built-in calls before execution.
      2. Code runs in a fresh subprocess (completely isolated from server memory).
      3. A hard timeout kills the subprocess if it runs too long.
      4. Combined stdout+stderr is capped at _MAX_OUTPUT_BYTES.
    """
    try:
        _check_code_safety(code)
    except ValueError as exc:
        return f"[Sandbox blocked] {exc}"

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return "[Sandbox error] Execution timed out."
    except Exception as exc:
        return f"[Sandbox error] Could not start subprocess: {exc}"

    out = (stdout or b"").decode("utf-8", errors="replace")
    err = (stderr or b"").decode("utf-8", errors="replace")
    combined = f"{out}\n[stderr]\n{err}".strip() if err else out.strip()

    if len(combined.encode()) > _MAX_OUTPUT_BYTES:
        combined = combined.encode()[:_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
        combined += "\n... [output truncated]"

    return combined or "(no output)"


# ── DB helpers for Tool ───────────────────────────────────────────────────────

async def save_tool(
    session: AsyncSession,
    name: str,
    description: str,
    code: str,
    parameters_schema: Dict[str, Any],
) -> str:
    """
    Validate and persist a tool to the DB.

    If a tool with the same name already exists it is updated in place.
    Returns a human-readable status message.
    """
    # Static safety check
    try:
        _check_code_safety(code)
    except ValueError as exc:
        return f"[Tool creation failed] {exc}"

    # Ensure the code defines a function with the expected name
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"[Tool creation failed] Syntax error: {exc}"

    defined = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    if name not in defined:
        return f"[Tool creation failed] Code must define a function named '{name}'."

    result = await session.execute(select(Tool).where(Tool.name == name))
    existing = result.scalar_one_or_none()
    if existing:
        existing.description = description
        existing.code = code
        existing.parameters_schema = parameters_schema
        await session.commit()
        return f"Tool '{name}' updated successfully."

    session.add(
        Tool(
            name=name,
            description=description,
            code=code,
            parameters_schema=parameters_schema,
        )
    )
    await session.commit()
    return f"Tool '{name}' created successfully."


async def get_all_tools(session: AsyncSession) -> List[Tool]:
    result = await session.execute(select(Tool).order_by(Tool.created_at))
    return list(result.scalars().all())


async def get_tool(session: AsyncSession, name: str) -> Optional[Tool]:
    result = await session.execute(select(Tool).where(Tool.name == name))
    return result.scalar_one_or_none()


async def _increment_call_count(session: AsyncSession, name: str) -> None:
    tool = await get_tool(session, name)
    if tool:
        tool.call_count = (tool.call_count or 0) + 1
        await session.commit()


# ── OpenAI function-calling definitions ──────────────────────────────────────

BUILTIN_TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Search the internet for information. Use this when you want to "
                "learn more about a topic, verify a fact, or deepen your understanding "
                "after being told something new."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results to fetch (1–10). Default is 5.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": (
                "Execute Python code in a sandbox and return its printed output. "
                "Use for calculations, data transformations, or testing logic before "
                "saving it as a reusable tool. "
                "Allowed modules: math, json, re, datetime, collections, itertools, "
                "functools, statistics, decimal, fractions, base64, hashlib, string, "
                "textwrap, random. "
                "Forbidden: os, sys, subprocess, socket, open(), eval(), exec()."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute. Must print its result.",
                    },
                    "description": {
                        "type": "string",
                        "description": "One-sentence description of what this code does.",
                    },
                },
                "required": ["code", "description"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_tool",
            "description": (
                "Define a new reusable Python tool that you can call in any future "
                "conversation. The tool is stored in your long-term memory. "
                "Use this when you identify a computation or transformation you will "
                "want to repeat. Test with execute_code first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "Unique snake_case function name "
                            "(e.g. 'convert_celsius_to_fahrenheit')."
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "What the tool does and when to use it.",
                    },
                    "code": {
                        "type": "string",
                        "description": (
                            "Python function definition. Must define exactly one function "
                            "whose name matches 'name'. The function must return (not print) "
                            "its result. Same sandbox restrictions as execute_code apply."
                        ),
                    },
                    "parameters_schema": {
                        "type": "object",
                        "description": (
                            "JSON Schema for the function's parameters, in OpenAI function "
                            "calling format (type, properties, required, additionalProperties)."
                        ),
                    },
                },
                "required": ["name", "description", "code", "parameters_schema"],
                "additionalProperties": False,
            },
        },
    },
    # ── Anti-hallucination tools ──────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "knowledge_verify",
            "description": (
                "Check if I have already learned something about a topic. "
                "Use this before claiming to know something to verify it's in my knowledge base. "
                "Returns all related knowledge items I have learned, or empty if nothing matches."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The topic to search for in my knowledge base (e.g., 'Python decorators', 'climate change').",
                    },
                    "keywords": {
                        "type": "string",
                        "description": "Optional: comma-separated keywords to search for (e.g., 'function, pattern, advanced').",
                    },
                },
                "required": ["topic"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fact_checker",
            "description": (
                "Verify the truthfulness of a claim by checking multiple sources: "
                "my learned knowledge, web search results, and logical consistency. "
                "Returns a structured verification report with confidence level."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "claim": {
                        "type": "string",
                        "description": "The statement/claim to verify (e.g., 'Python is a dynamically typed language').",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this claim needs verification (e.g., 'about to teach the user', 'from web search').",
                    },
                },
                "required": ["claim"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confidence_score",
            "description": (
                "Assign a confidence score (0-100) to my response based on: "
                "whether it's from my knowledge base, how certain I am, potential risks. "
                "Returns confidence score and reasoning."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "statement": {
                        "type": "string",
                        "description": "The statement I'm about to make or just made.",
                    },
                    "source": {
                        "type": "string",
                        "description": "Where this statement comes from: 'learned', 'web_search', 'reasoning', 'inference'.",
                    },
                },
                "required": ["statement", "source"],
                "additionalProperties": False,
            },
        },
    },
]


async def get_all_tool_definitions(session: AsyncSession) -> List[Dict[str, Any]]:
    """Return built-in definitions plus a definition for every created tool."""
    defs = list(BUILTIN_TOOL_DEFINITIONS)
    for tool in await get_all_tools(session):
        defs.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters_schema or {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        })
    return defs


async def dispatch_tool(
    session: AsyncSession,
    tool_name: str,
    args: Dict[str, Any],
    code_exec_timeout: int = 10,
) -> str:
    """Route a function-call from the LLM to the correct implementation."""
    if tool_name == "web_search":
        results = await web_search(
            query=args.get("query", ""),
            max_results=int(args.get("max_results", 5)),
        )
        return format_search_results(results)

    if tool_name == "execute_code":
        return await execute_code_sandboxed(
            args.get("code", ""), timeout=code_exec_timeout
        )

    if tool_name == "create_tool":
        return await save_tool(
            session,
            name=args.get("name", ""),
            description=args.get("description", ""),
            code=args.get("code", ""),
            parameters_schema=args.get("parameters_schema", {}),
        )

    # ────── Anti-hallucination tools ──────────────────────────────────────────
    if tool_name == "knowledge_verify":
        return await _handle_knowledge_verify(session, args)

    if tool_name == "fact_checker":
        return await _handle_fact_checker(session, args)

    if tool_name == "confidence_score":
        return await _handle_confidence_score(session, args)

    # Custom (created) tool — inject its function definition then call it
    tool = await get_tool(session, tool_name)
    if tool is None:
        return f"[Error] Unknown tool '{tool_name}'."

    invocation = (
        f"{tool.code}\n"
        f"_result = {tool.name}(**{json.dumps(args)})\n"
        f"print(_result)"
    )
    output = await execute_code_sandboxed(invocation, timeout=code_exec_timeout)
    await _increment_call_count(session, tool_name)
    return output


# ────────────────────────────────────────────────────────────────────────────────
# Anti-hallucination Tool Handlers
# ────────────────────────────────────────────────────────────────────────────────


async def _handle_knowledge_verify(session: AsyncSession, args: Dict[str, Any]) -> str:
    """
    Check if the AI has already learned something about a topic.
    Searches the KnowledgeItem table for matching knowledge.
    
    Args:
        args: {
            "topic": str - the topic to search for,
            "keywords": str (optional) - comma-separated keywords
        }
    
    Returns:
        JSON string with verification results
    """
    topic = args.get("topic", "").strip()
    keywords = args.get("keywords", "").strip()

    if not topic:
        return json.dumps({"found": False, "reason": "No topic provided"})

    # 检查缓存
    cache_key = f"{topic}|{keywords}"
    if cache_key in _knowledge_cache:
        cached_time, cached_data = _knowledge_cache[cache_key]
        # 缓存 5 分钟有效
        import time
        if time.time() - cached_time < 300:
            return json.dumps(cached_data)

    try:
        from models import KnowledgeItem

        # Search for existing knowledge on this topic
        query = select(KnowledgeItem).where(
            KnowledgeItem.topic.ilike(f"%{topic}%")
        )
        result = await session.execute(query)
        knowledge_items = result.scalars().all()

        if not knowledge_items:
            result_data = {
                "found": False,
                "topic": topic,
                "count": 0,
                "recommendation": "This is new knowledge to learn!",
            }
            _knowledge_cache[cache_key] = (
                __import__("time").time(), 
                result_data
            )
            return json.dumps(result_data)

        # Filter by keywords if provided
        if keywords:
            keyword_list = [k.strip().lower() for k in keywords.split(",")]
            filtered_items = [
                item
                for item in knowledge_items
                if any(
                    kw in item.content.lower()
                    for kw in keyword_list
                )
            ]
        else:
            filtered_items = knowledge_items

        # Return found knowledge with details
        result_data = {
            "found": True,
            "topic": topic,
            "count": len(filtered_items),
            "knowledge_items": [
                {
                    "id": item.id,
                    "content_preview": item.content[:200] + "..."
                    if len(item.content) > 200
                    else item.content,
                    "created_at": item.timestamp.isoformat()
                    if item.timestamp
                    else None,
                }
                for item in filtered_items[:5]  # Return top 5
            ],
            "recommendation": f"I already know {len(filtered_items)} things about '{topic}'.",
        }
        # 缓存结果
        _knowledge_cache[cache_key] = (__import__("time").time(), result_data)
        return json.dumps(result_data)
    except Exception as e:
        return json.dumps(
            {"error": f"Knowledge verification failed: {str(e)}"}
        )


async def _handle_fact_checker(session: AsyncSession, args: Dict[str, Any]) -> str:
    """
    Verify a claim by checking against learned knowledge and web search.
    Returns confidence level and source information.
    
    Args:
        args: {
            "claim": str - the statement to verify,
            "reason": str (optional) - why verification is needed
        }
    
    Returns:
        JSON string with verification results and confidence score
    """
    claim = args.get("claim", "").strip()
    reason = args.get("reason", "").strip()

    if not claim:
        return json.dumps({"verified": False, "reason": "No claim provided"})

    try:
        from models import KnowledgeItem

        # Extract key terms from the claim (simple keyword extraction)
        key_terms = [
            word
            for word in claim.split()
            if len(word) > 3 and word.lower() not in {"this", "that"}
        ][:3]

        # Check against learned knowledge
        knowledge_found = []
        for term in key_terms:
            query = select(KnowledgeItem).where(
                KnowledgeItem.content.ilike(f"%{term}%")
            )
            result = await session.execute(query)
            knowledge_found.extend(result.scalars().all())

        knowledge_confidence = (
            min(100, len(knowledge_found) * 30) if knowledge_found else 0
        )

        # Try web search for additional verification
        search_results = []
        try:
            search_results = await web_search(
                query=claim, max_results=3
            )
        except Exception:
            pass  # Web search is optional

        web_confidence = (
            min(100, len(search_results) * 25)
            if search_results
            else 0
        )

        # Combined confidence score
        overall_confidence = max(knowledge_confidence, web_confidence)

        result = {
            "claim": claim,
            "verified": overall_confidence >= 50,
            "confidence_score": overall_confidence,
            "sources": {
                "learned_knowledge": len(knowledge_found),
                "web_search_results": len(search_results),
            },
            "recommendation": (
                "This claim is well-supported by my knowledge."
                if overall_confidence >= 75
                else "This claim needs more verification before sharing."
                if overall_confidence < 50
                else "This claim is partially verified."
            ),
        }

        if reason:
            result["reason"] = reason

        return json.dumps(result)
    except Exception as e:
        return json.dumps(
            {"error": f"Fact checking failed: {str(e)}"}
        )


async def _handle_confidence_score(
    session: AsyncSession, args: Dict[str, Any]
) -> str:
    """
    Assign a confidence score to a statement based on its source and status.
    Helps the AI decide whether to present information as fact, opinion, or uncertain.
    
    Args:
        args: {
            "statement": str - the statement to score,
            "source": str - source type: 'learned', 'web_search', 'reasoning', 'inference'
        }
    
    Returns:
        JSON string with confidence score and reasoning
    """
    statement = args.get("statement", "").strip()
    source = args.get("source", "reasoning").lower().strip()

    if not statement:
        return json.dumps({"score": 0, "reason": "No statement provided"})

    # Base confidence scores by source
    source_confidence = {
        "learned": 85,  # High confidence - verified knowledge
        "web_search": 60,  # Medium confidence - internet may be unreliable
        "reasoning": 40,  # Lower confidence - logical deduction
        "inference": 30,  # Low confidence - educated guess
    }

    base_score = source_confidence.get(source, 40)

    # Adjust based on statement characteristics
    adjustment = 0

    # Specific claims are more verifiable than vague ones (支持中英文)
    word_count = len(statement.split())
    if word_count >= 20:  # 中文字符数更多
        adjustment += 10
    elif word_count <= 3:
        adjustment -= 10

    # Statements with uncertainty markers should have lower scores
    # 支持中英文的不确定性标记
    uncertainty_markers = [
        # English
        "might", "maybe", "possibly", "probably", "seems like", "could be", "I think", "I believe",
        # Chinese
        "可能", "也许", "好像", "似乎", "大概", "或许", "我认为", "我觉得", "不确定",
    ]

    statement_lower = statement.lower()
    if any(marker in statement_lower for marker in uncertainty_markers):
        adjustment -= 20

    # Statements with specific evidence markers get higher scores
    # 支持中英文的证据标记
    evidence_markers = [
        # English
        "according to", "research shows", "studies indicate", "evidence", "proven", "confirmed",
        # Chinese
        "根据", "研究表明", "证据", "已证实", "确认", "表明", "显示",
    ]
    if any(marker in statement_lower for marker in evidence_markers):
        adjustment += 15

    # Calculate final score (0-100)
    final_score = max(0, min(100, base_score + adjustment))

    # Determine presentation style based on score
    if final_score >= 80:
        presentation = "FACT"
        phrasing = (
            "I can confidently state that..."
        )
    elif final_score >= 60:
        presentation = "LIKELY"
        phrasing = "Based on what I know, it's likely that..."
    elif final_score >= 40:
        presentation = "POSSIBLE"
        phrasing = "It's possible that... but I'm not entirely sure."
    else:
        presentation = "UNCERTAIN"
        phrasing = "I'm not confident about this, but it could be..."

    return json.dumps(
        {
            "statement": statement,
            "source": source,
            "confidence_score": final_score,
            "presentation_style": presentation,
            "suggested_phrasing": phrasing,
            "recommendation": (
                "Share this confidently."
                if final_score >= 75
                else "Share with appropriate caveats."
                if final_score >= 50
                else "Do better research before sharing."
            ),
        }
    )
