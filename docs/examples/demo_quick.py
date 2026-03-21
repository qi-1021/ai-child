#!/usr/bin/env python3
"""
🎯 Anti-Hallucination Tools - Quick Demo
==========================================

This is a simplified, standalone demo that shows how the three anti-hallucination
tools work without requiring full database setup.

Run with: python demo_quick.py
"""

import json
import random


class MockKnowledgeItem:
    """Mock knowledge item for demo."""
    def __init__(self, id, topic, content):
        self.id = id
        self.topic = topic
        self.content = content
        self.created_at = "2024-01-15T10:30:00+00:00"


# Simulated knowledge base
MOCK_KNOWLEDGE_BASE = [
    MockKnowledgeItem(1, "Python Programming", 
                     "Python is a high-level programming language known for its readability and simplicity."),
    MockKnowledgeItem(2, "Python Decorators",
                     "A decorator is a function that takes another function as input and returns an enhanced version."),
    MockKnowledgeItem(3, "Machine Learning",
                     "Machine Learning is a subset of AI that enables systems to learn and improve from experience."),
    MockKnowledgeItem(4, "Web Development",
                     "Web development involves creating and maintaining websites and web applications."),
]


def demo_knowledge_verify(topic: str, keywords: str = None) -> dict:
    """Demo: Check if knowledge about a topic exists."""
    print(f"\n🔍 [knowledge_verify] Topic: '{topic}'")
    if keywords:
        print(f"   Keywords: {keywords}")
    
    # Search knowledge base
    matching = [item for item in MOCK_KNOWLEDGE_BASE 
                if topic.lower() in item.topic.lower()]
    
    if not matching:
        result = {
            "found": False,
            "topic": topic,
            "count": 0,
            "recommendation": "This is new knowledge to learn!"
        }
    else:
        # Filter by keywords if provided
        if keywords:
            keyword_list = [k.strip().lower() for k in keywords.split(",")]
            filtered = [item for item in matching 
                       if any(kw in item.content.lower() for kw in keyword_list)]
        else:
            filtered = matching
        
        result = {
            "found": True,
            "topic": topic,
            "count": len(filtered),
            "knowledge_items": [
                {
                    "id": item.id,
                    "content_preview": item.content[:80] + "...",
                    "created_at": item.created_at
                }
                for item in filtered
            ],
            "recommendation": f"I already know {len(filtered)} things about '{topic}'."
        }
    
    print(f"   ✅ Result: {result['recommendation']}")
    return result


def demo_confidence_score(statement: str, source: str = "reasoning") -> dict:
    """Demo: Assess confidence level of a statement."""
    print(f"\n📊 [confidence_score] Statement: '{statement[:50]}...'")
    print(f"   Source: {source}")
    
    # Base scores by source
    base_scores = {
        "learned": 85,
        "web_search": 60,
        "reasoning": 40,
        "inference": 30,
    }
    
    base_score = base_scores.get(source, 40)
    adjustment = 0
    
    # Check for uncertainty markers (English)
    uncertainty_markers = ["might", "maybe", "possibly", "I think", "I believe"]
    uncertainty_markers_cn = ["可能", "也许", "我认为", "好像", "似乎"]
    
    if any(m in statement.lower() for m in uncertainty_markers) or \
       any(m in statement for m in uncertainty_markers_cn):
        adjustment -= 20
    
    # Check for evidence markers (English)
    evidence_markers = ["according to", "research shows", "evidence", "proven"]
    evidence_markers_cn = ["根据", "研究表明", "证据", "确认"]
    
    if any(m in statement.lower() for m in evidence_markers) or \
       any(m in statement for m in evidence_markers_cn):
        adjustment += 15
    
    final_score = max(0, min(100, base_score + adjustment))
    
    # Determine style
    if final_score >= 80:
        style = "FACT"
        phrasing = "I can confidently state that..."
    elif final_score >= 60:
        style = "LIKELY"
        phrasing = "Based on what I know, it's likely that..."
    elif final_score >= 40:
        style = "POSSIBLE"
        phrasing = "It's possible that... but I'm not entirely sure."
    else:
        style = "UNCERTAIN"
        phrasing = "I'm uncertain about this, but it could be..."
    
    result = {
        "statement": statement,
        "source": source,
        "confidence_score": final_score,
        "presentation_style": style,
        "suggested_phrasing": phrasing,
    }
    
    print(f"   📈 Confidence: {final_score}/100 | Style: {style}")
    return result


def demo_fact_checker(claim: str) -> dict:
    """Demo: Check if a claim is verifiable."""
    print(f"\n✔️  [fact_checker] Claim: '{claim}'")
    
    # Simple truthfulness check
    is_obviously_false = any(phrase in claim.lower() for phrase in [
        "was invented yesterday", "is completely wrong", "doesn't exist"
    ])
    
    if is_obviously_false:
        confidence = 5
        verified = False
    else:
        # Check against knowledge base
        matching_items = sum(1 for item in MOCK_KNOWLEDGE_BASE 
                            if any(word in claim.lower() for word in item.topic.lower().split()))
        confidence = min(95, 50 + matching_items * 15)
        verified = confidence >= 50
    
    result = {
        "claim": claim,
        "verified": verified,
        "confidence_score": confidence,
        "sources": {
            "learned_knowledge": 3 if verified else 0,
            "web_search_results": 5 if verified else 0,
        },
        "recommendation": (
            "This claim is well-supported by my knowledge."
            if confidence >= 75
            else "This claim needs more verification before sharing."
            if confidence < 50
            else "This claim is partially verified."
        )
    }
    
    print(f"   ✅ Verified: {verified} | Confidence: {confidence}/100")
    return result


def main():
    """Run the demo."""
    
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║     🧠 Anti-Hallucination Tools Quick Demo - No Database Required         ║
╚════════════════════════════════════════════════════════════════════════════╝
    """)
    
    # Demo 1: Knowledge Verify
    print("\n" + "=" * 80)
    print("DEMO 1️⃣  - knowledge_verify: Check What You Know")
    print("=" * 80)
    
    demo1_tests = [
        ("Python Programming", None),
        ("Python Decorators", "function, pattern"),
        ("Quantum Computing", None),
    ]
    
    for topic, keywords in demo1_tests:
        result = demo_knowledge_verify(topic, keywords)
        print(f"   Raw JSON: {json.dumps(result, indent=2)}\n")
    
    # Demo 2: Confidence Score
    print("\n" + "=" * 80)
    print("DEMO 2️⃣  - confidence_score: Rate Your Confidence")
    print("=" * 80)
    
    demo2_tests = [
        ("Paris is the capital of France", "learned"),
        ("I think it might rain tomorrow", "inference"),
        ("According to research, Python is popular", "web_search"),
        ("Python 可能是最好的编程语言", "reasoning"),
    ]
    
    for statement, source in demo2_tests:
        result = demo_confidence_score(statement, source)
        print(f"   Raw JSON: {json.dumps(result, indent=2)}\n")
    
    # Demo 3: Fact Checker
    print("\n" + "=" * 80)
    print("DEMO 3️⃣  - fact_checker: Verify Facts")
    print("=" * 80)
    
    demo3_tests = [
        "Python is a programming language",
        "Machine Learning uses AI techniques",
        "Web development is a programming practice",
        "Python was invented yesterday",
    ]
    
    for claim in demo3_tests:
        result = demo_fact_checker(claim)
        print(f"   Raw JSON: {json.dumps(result, indent=2)}\n")
    
    # Demo 4: Real-world scenario
    print("\n" + "=" * 80)
    print("DEMO 4️⃣  - Real Scenario: Complete AI Response")
    print("=" * 80)
    
    print("\n📝 User Question: '告诉我关于Python的情况' (Tell me about Python)\n")
    
    print("🤖 AI Internal Process:\n")
    
    # Step 1: Verify knowledge
    print("  Step 1: Check existing knowledge about Python")
    step1 = demo_knowledge_verify("Python")
    print(f"    → Decision: Use existing knowledge (found {step1['count']} items)\n")
    
    # Step 2: Verify a claim
    print("  Step 2: Verify the claim before stating it")
    step2 = demo_fact_checker("Python is a programming language")
    print(f"    → Decision: Confidence {step2['confidence_score']}% - OK to share\n")
    
    # Step 3: Assess confidence for response
    print("  Step 3: Assess confidence for how to present the answer")
    step3 = demo_confidence_score("Python is widely used in machine learning and web development", "learned")
    print(f"    → Recommendation: Use phrase '{step3['suggested_phrasing']}'\n")
    
    print("💬 AI Final Response:\n")
    print("""
    I can confidently state that Python is a programming language known for its 
    readability and simplicity. I've already learned several things about Python, 
    including that it's widely used in machine learning and web development.
    
    [QUESTION: Which aspect of Python interests you most - web development, 
    data science, or something else?]
    """)
    
    # Statistics
    print("\n" + "=" * 80)
    print("📊 Performance Summary")
    print("=" * 80)
    print("""
Tool Performance (Mock):
  ✅ knowledge_verify:  ~5ms   (simulated database query)
  ✅ fact_checker:      ~2ms   (simulated fact check)
  ✅ confidence_score:  ~1ms   (local calculation)

Language Support:
  ✅ English
  ✅ 中文 (Chinese)
  ✅ Mixed language support

Benefits:
  ✅ Reduces hallucinations by verifying claims
  ✅ Provides confidence levels for transparency
  ✅ Grows knowledge base over time
  ✅ Adapts response tone based on certainty
  ✅ Fully async-compatible with FastAPI
    """)
    
    print("\n✨ Demo completed successfully!")
    print("\n💡 Next steps:")
    print("   1. Run the full demo: python demo_antihallucination.py")
    print("   2. Integrate with your AI system")
    print("   3. Monitor hallucination reduction rates")
    print("   4. Proceed to Phase 2: Chinese optimization\n")


if __name__ == "__main__":
    main()
