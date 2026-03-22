"""
Tests for anti-hallucination tools: knowledge_verify, fact_checker, confidence_score.
"""
import pytest
from sqlalchemy import select
from models import KnowledgeItem

# We'll test the actual dispatch_tool function to ensure these tools work
# within the tool system.


@pytest.mark.asyncio
async def test_knowledge_verify_no_match(session):
    """Test knowledge_verify returns empty when no matching knowledge exists."""
    from ai.tools import dispatch_tool
    
    result = await dispatch_tool(
        session,
        "knowledge_verify",
        {"topic": "nonexistent_topic_xyz_123"},
    )
    
    import json
    result_data = json.loads(result)
    assert result_data["found"] is False
    assert result_data["count"] == 0


@pytest.mark.asyncio
async def test_knowledge_verify_with_match(session):
    """Test knowledge_verify returns matching knowledge."""
    from ai.tools import dispatch_tool
    
    # Create a test knowledge item
    knowledge = KnowledgeItem(
        topic="Python Decorators",
        content="A decorator is a function that takes another function as input...",
    )
    session.add(knowledge)
    await session.commit()
    
    # Now verify
    result = await dispatch_tool(
        session,
        "knowledge_verify",
        {"topic": "Python Decorators"},
    )
    
    import json
    result_data = json.loads(result)
    assert result_data["found"] is True
    assert result_data["count"] >= 1


@pytest.mark.asyncio
async def test_fact_checker_basic(session):
    """Test fact_checker returns a confidence score."""
    from ai.tools import dispatch_tool
    
    result = await dispatch_tool(
        session,
        "fact_checker",
        {
            "claim": "Python is a programming language",
            "reason": "testing",
        },
    )
    
    import json
    result_data = json.loads(result)
    assert "confidence_score" in result_data
    assert 0 <= result_data["confidence_score"] <= 100
    assert "verified" in result_data
    assert "sources" in result_data


@pytest.mark.asyncio
async def test_confidence_score_learned(session):
    """Test confidence_score for statements from learned knowledge."""
    from ai.tools import dispatch_tool
    
    result = await dispatch_tool(
        session,
        "confidence_score",
        {
            "statement": "The capital of France is Paris",
            "source": "learned",
        },
    )
    
    import json
    result_data = json.loads(result)
    assert "confidence_score" in result_data
    assert result_data["confidence_score"] >= 75  # High confidence for learned
    assert "presentation_style" in result_data
    assert result_data["presentation_style"] == "FACT"


@pytest.mark.asyncio
async def test_confidence_score_inference(session):
    """Test confidence_score for inferred statements."""
    from ai.tools import dispatch_tool
    
    result = await dispatch_tool(
        session,
        "confidence_score",
        {
            "statement": "If it rains tomorrow, the ground will be wet",
            "source": "inference",
        },
    )
    
    import json
    result_data = json.loads(result)
    assert "confidence_score" in result_data
    assert 0 <= result_data["confidence_score"] <= 50  # Low confidence for inference
    assert "presentation_style" in result_data
    assert result_data["presentation_style"] in ["POSSIBLE", "UNCERTAIN"]


@pytest.mark.asyncio
async def test_confidence_score_with_uncertainty_markers(session):
    """Test confidence_score reduces score when uncertainty markers present."""
    from ai.tools import dispatch_tool
    
    result1 = await dispatch_tool(
        session,
        "confidence_score",
        {
            "statement": "Python is a programming language",
            "source": "learned",
        },
    )
    
    result2 = await dispatch_tool(
        session,
        "confidence_score",
        {
            "statement": "I think Python might be a programming language",
            "source": "learned",
        },
    )
    
    import json
    data1 = json.loads(result1)
    data2 = json.loads(result2)
    
    # Statement with uncertainty markers should have lower score
    assert data2["confidence_score"] < data1["confidence_score"]


@pytest.mark.asyncio
async def test_tool_definitions_present():
    """Test that all three anti-hallucination tools are in BUILTIN_TOOL_DEFINITIONS."""
    from ai import tools
    
    tool_names = [
        t['function']['name'] 
        for t in tools.BUILTIN_TOOL_DEFINITIONS 
        if 'function' in t
    ]
    
    assert "knowledge_verify" in tool_names
    assert "fact_checker" in tool_names
    assert "confidence_score" in tool_names


@pytest.mark.asyncio
async def test_handler_functions_exist():
    """Test that handler functions are defined."""
    from ai import tools
    
    assert hasattr(tools, '_handle_knowledge_verify')
    assert hasattr(tools, '_handle_fact_checker')
    assert hasattr(tools, '_handle_confidence_score')
    assert callable(tools._handle_knowledge_verify)
    assert callable(tools._handle_fact_checker)
    assert callable(tools._handle_confidence_score)
