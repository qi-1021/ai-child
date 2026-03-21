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
