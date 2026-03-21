#!/usr/bin/env python3
"""
Direct verification of anti-hallucination tools implementation.
Run this script to verify that the three new tools are correctly integrated.
"""
import sys
import json

def verify_tools():
    """Verify anti-hallucination tools are integrated."""
    sys.path.insert(0, '/Volumes/mac第二磁盘/ai-child/server')
    
    try:
        from ai import tools
        print("✓ tools module imported successfully")
        
        # Check if tool definitions exist
        tool_names = [
            t['function']['name'] 
            for t in tools.BUILTIN_TOOL_DEFINITIONS 
            if 'function' in t
        ]
        
        print(f"\n✓ Total built-in tools: {len([t for t in tools.BUILTIN_TOOL_DEFINITIONS if 'function' in t])}")
        print(f"  All tools: {json.dumps(tool_names, indent=2)}")
        
        # Check for new tools
        print("\n📋 Anti-hallucination tools verification:")
        new_tools = ['knowledge_verify', 'fact_checker', 'confidence_score']
        all_present = True
        for tool_name in new_tools:
            if tool_name in tool_names:
                print(f"  ✓ {tool_name}")
                # Get feature description
                for tool_def in tools.BUILTIN_TOOL_DEFINITIONS:
                    if 'function' in tool_def and tool_def['function']['name'] == tool_name:
                        desc = tool_def['function']['description'][:80] + "..."
                        print(f"    → {desc}")
                        break
            else:
                print(f"  ✗ {tool_name} NOT FOUND")
                all_present = False
        
        # Verify handler functions exist
        print("\n📚 Handler functions verification:")
        handlers = [
            '_handle_knowledge_verify',
            '_handle_fact_checker', 
            '_handle_confidence_score'
        ]
        for handler_name in handlers:
            if hasattr(tools, handler_name):
                handler = getattr(tools, handler_name)
                print(f"  ✓ {handler_name} (callable: {callable(handler)})")
            else:
                print(f"  ✗ {handler_name} NOT FOUND")
                all_present = False
        
        if all_present:
            print("\n✅ SUCCESS: All anti-hallucination tools properly integrated!")
            print("\n📝 Usage in LLM context:")
            print("   When the AI is uncertain, it can call these tools:")
            print("   1. knowledge_verify(topic) → Check if something is in learned knowledge")
            print("   2. fact_checker(claim) → Verify claim vs knowledge + web search")
            print("   3. confidence_score(statement, source) → Get confidence level before sharing")
            return True
        else:
            print("\n❌ FAILURE: Some tools are missing!")
            return False
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = verify_tools()
    sys.exit(0 if success else 1)
