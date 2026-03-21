"""
Tests for the tool system (ai/tools.py) and autonomous researcher (ai/researcher.py).
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Tool


# ── In-memory DB fixture ──────────────────────────────────────────────────────

@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s


# ── _check_code_safety ────────────────────────────────────────────────────────

def test_safe_code_passes():
    from ai.tools import _check_code_safety
    _check_code_safety("import math\nprint(math.sqrt(4))")


def test_blocked_module_import_raises():
    from ai.tools import _check_code_safety
    with pytest.raises(ValueError, match="os"):
        _check_code_safety("import os\nos.system('ls')")


def test_blocked_from_import_raises():
    from ai.tools import _check_code_safety
    with pytest.raises(ValueError, match="subprocess"):
        _check_code_safety("from subprocess import run")


def test_blocked_builtin_call_raises():
    from ai.tools import _check_code_safety
    with pytest.raises(ValueError, match="eval"):
        _check_code_safety("result = eval('1+1')")


def test_blocked_open_raises():
    from ai.tools import _check_code_safety
    with pytest.raises(ValueError, match="open"):
        _check_code_safety("f = open('secret.txt')")


def test_blocked_dunder_attr_raises():
    from ai.tools import _check_code_safety
    with pytest.raises(ValueError, match="__globals__"):
        _check_code_safety("x = (lambda: None).__globals__")


def test_syntax_error_raises():
    from ai.tools import _check_code_safety
    with pytest.raises(ValueError, match="Syntax error"):
        _check_code_safety("def foo(: pass")


# ── execute_code_sandboxed ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_execute_simple_code():
    from ai.tools import execute_code_sandboxed
    result = await execute_code_sandboxed("print(2 + 2)")
    assert result == "4"


@pytest.mark.asyncio
async def test_execute_math_import():
    from ai.tools import execute_code_sandboxed
    result = await execute_code_sandboxed("import math\nprint(round(math.pi, 4))")
    assert "3.1416" in result


@pytest.mark.asyncio
async def test_execute_dangerous_code_blocked_before_subprocess():
    from ai.tools import execute_code_sandboxed
    result = await execute_code_sandboxed("import os\nprint(os.getcwd())")
    assert "[Sandbox blocked]" in result


@pytest.mark.asyncio
async def test_execute_timeout():
    from ai.tools import execute_code_sandboxed
    result = await execute_code_sandboxed("while True: pass", timeout=1)
    assert "timed out" in result.lower()


@pytest.mark.asyncio
async def test_execute_no_output():
    from ai.tools import execute_code_sandboxed
    result = await execute_code_sandboxed("x = 1 + 1")
    assert result == "(no output)"


# ── format_search_results ─────────────────────────────────────────────────────

def test_format_search_results_empty():
    from ai.tools import format_search_results
    assert format_search_results([]) == "No results found."


def test_format_search_results_populated():
    from ai.tools import format_search_results
    results = [
        {"title": "Test Title", "href": "https://example.com", "body": "Some text."}
    ]
    formatted = format_search_results(results)
    assert "Test Title" in formatted
    assert "https://example.com" in formatted
    assert "Some text." in formatted


# ── save_tool ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_tool_creates_entry(session):
    from ai.tools import save_tool, get_tool

    code = "def add_numbers(a, b):\n    return a + b"
    schema = {
        "type": "object",
        "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
        "required": ["a", "b"],
    }
    msg = await save_tool(session, "add_numbers", "Adds two numbers.", code, schema)
    assert "created" in msg

    tool = await get_tool(session, "add_numbers")
    assert tool is not None
    assert tool.name == "add_numbers"
    assert tool.call_count == 0


@pytest.mark.asyncio
async def test_save_tool_updates_existing(session):
    from ai.tools import save_tool, get_tool

    code = "def greet(name):\n    return f'Hello, {name}'"
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    await save_tool(session, "greet", "Greet.", code, schema)

    new_code = "def greet(name):\n    return f'Hi, {name}!'"
    msg = await save_tool(session, "greet", "Greet v2.", new_code, schema)
    assert "updated" in msg

    tool = await get_tool(session, "greet")
    assert "Hi" in tool.code


@pytest.mark.asyncio
async def test_save_tool_wrong_function_name_rejected(session):
    from ai.tools import save_tool

    code = "def wrong_name(x):\n    return x"
    msg = await save_tool(session, "my_tool", "desc", code, {})
    assert "failed" in msg.lower()


@pytest.mark.asyncio
async def test_save_tool_dangerous_code_rejected(session):
    from ai.tools import save_tool

    code = "def hack():\n    import os\n    return os.getcwd()"
    msg = await save_tool(session, "hack", "desc", code, {})
    assert "failed" in msg.lower()


# ── get_all_tool_definitions ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_all_tool_definitions_includes_builtins(session):
    from ai.tools import get_all_tool_definitions, BUILTIN_TOOL_DEFINITIONS

    defs = await get_all_tool_definitions(session)
    builtin_names = {d["function"]["name"] for d in BUILTIN_TOOL_DEFINITIONS}
    def_names = {d["function"]["name"] for d in defs}
    assert builtin_names.issubset(def_names)


@pytest.mark.asyncio
async def test_get_all_tool_definitions_includes_created_tools(session):
    from ai.tools import get_all_tool_definitions, save_tool

    code = "def cube(n):\n    return n ** 3"
    schema = {"type": "object", "properties": {"n": {"type": "number"}}, "required": ["n"]}
    await save_tool(session, "cube", "Cubes a number.", code, schema)

    defs = await get_all_tool_definitions(session)
    names = [d["function"]["name"] for d in defs]
    assert "cube" in names


# ── dispatch_tool ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dispatch_web_search(session):
    from ai.tools import dispatch_tool

    fake_results = [{"title": "Python", "href": "https://python.org", "body": "Official site"}]
    with patch("ai.tools.web_search", new=AsyncMock(return_value=fake_results)):
        result = await dispatch_tool(session, "web_search", {"query": "Python language"})
    assert "Python" in result


@pytest.mark.asyncio
async def test_dispatch_execute_code(session):
    from ai.tools import dispatch_tool

    result = await dispatch_tool(
        session,
        "execute_code",
        {"code": "print(10 * 10)", "description": "Multiply"},
    )
    assert "100" in result


@pytest.mark.asyncio
async def test_dispatch_create_tool(session):
    from ai.tools import dispatch_tool, get_tool

    code = "def square(n):\n    return n * n"
    schema = {"type": "object", "properties": {"n": {"type": "number"}}, "required": ["n"]}
    result = await dispatch_tool(
        session,
        "create_tool",
        {"name": "square", "description": "Square a number.", "code": code, "parameters_schema": schema},
    )
    assert "created" in result
    tool = await get_tool(session, "square")
    assert tool is not None


@pytest.mark.asyncio
async def test_dispatch_custom_tool(session):
    from ai.tools import dispatch_tool, save_tool

    code = "def double(x):\n    return x * 2"
    schema = {"type": "object", "properties": {"x": {"type": "number"}}, "required": ["x"]}
    await save_tool(session, "double", "Doubles a number.", code, schema)

    result = await dispatch_tool(session, "double", {"x": 21})
    assert "42" in result


@pytest.mark.asyncio
async def test_dispatch_unknown_tool(session):
    from ai.tools import dispatch_tool

    result = await dispatch_tool(session, "does_not_exist", {})
    assert "Unknown tool" in result or "not found" in result.lower()


# ── Researcher ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_research_topic_stores_knowledge():
    """
    research_topic should call web_search, summarise results, and store
    a self-sourced KnowledgeItem.
    """
    from ai import researcher as res_module

    fake_results = [
        {"title": "Gravity", "href": "https://example.com/gravity", "body": "Objects attract."}
    ]
    fake_summary = "Gravity is the force attracting objects with mass."

    mock_queries_choice = MagicMock()
    mock_queries_choice.message.content = '["gravity physics", "Newton gravity law"]'
    mock_queries_resp = MagicMock()
    mock_queries_resp.choices = [mock_queries_choice]

    mock_summary_choice = MagicMock()
    mock_summary_choice.message.content = fake_summary
    mock_summary_resp = MagicMock()
    mock_summary_resp.choices = [mock_summary_choice]

    with (
        patch.object(res_module.client.chat.completions, "create", new=AsyncMock(
            side_effect=[mock_queries_resp, mock_summary_resp]
        )),
        patch("ai.researcher.web_search", new=AsyncMock(return_value=fake_results)),
        patch("ai.researcher.settings") as mock_settings,
        patch("ai.researcher.async_session") as mock_session_factory,
        patch("ai.researcher.add_knowledge", new=AsyncMock()) as mock_add,
    ):
        mock_settings.research_enabled = True
        mock_settings.openai_model = "gpt-4o"
        mock_settings.research_query_count = 2
        mock_settings.research_max_results = 3

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_factory.return_value = mock_session

        await res_module.research_topic("gravity", "Objects fall at 9.8 m/s²")
        mock_add.assert_called_once()
        call_kwargs = mock_add.call_args.kwargs
        assert call_kwargs["source"] == "self"
        assert call_kwargs["topic"] == "gravity"


@pytest.mark.asyncio
async def test_research_topic_skipped_when_disabled():
    from ai import researcher as res_module

    with patch("ai.researcher.settings") as mock_settings:
        mock_settings.research_enabled = False
        with patch("ai.researcher.web_search", new=AsyncMock()) as mock_search:
            await res_module.research_topic("any_topic", "any_answer")
            mock_search.assert_not_called()
