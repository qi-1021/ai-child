#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export AI Child personality profile for backup and GitHub syncing.

Usage:
    python export_personality.py                    # Export to JSON
    python export_personality.py --backup-dir .     # Export to directory
    python export_personality.py --format yaml      # Export as YAML
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional
import argparse

# Add server to path
server_path = Path(__file__).parent / "server"
sys.path.insert(0, str(server_path))

from sqlalchemy import select
from models import PersonalityMemory, AIProfile, init_db, async_session
from ai.personality_memory import PersonalityMemoryManager


async def export_personality_data(
    format: str = "json",
) -> dict:
    """Export personality profile from database."""
    
    async with async_session() as session:
        # Initialize DB if needed
        await init_db()
        
        manager = PersonalityMemoryManager(session)
        export_data = await manager.export_personality_profile()
        
        return export_data


def save_export(
    data: dict,
    output_path: Path,
    format: str = "json",
) -> None:
    """Save exported data to file."""
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if format == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"✅ Exported to {output_path}")
    
    elif format == "yaml":
        try:
            import yaml
            with open(output_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
            print(f"✅ Exported to {output_path}")
        except ImportError:
            print("❌ YAML format requires 'pip install pyyaml'")
            sys.exit(1)
    
    elif format == "markdown":
        # Export as formatted Markdown for easy reading
        content = _format_as_markdown(data)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ Exported to {output_path}")


def _format_as_markdown(data: dict) -> str:
    """Format personality data as Markdown."""
    profile = data.get("profile", {})
    memories = data.get("memories", [])
    
    md_parts = [
        "# AI Child 人格档案 (Personality Profile)",
        "",
        "## 基本信息 / Basic Information",
        f"- **名字** / Name: {profile.get('name', '未命名 / Unnamed')}",
        f"- **语言** / Language: {profile.get('language', 'en-US')}",
        f"- **创建时间** / Created: {profile.get('created_at', 'N/A')}",
        "",
        "## 个性特征 / Personality Traits",
        "```json",
        json.dumps(profile.get('personality_traits', {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## 人格记忆 / Personality Memories",
        "",
    ]
    
    # Group by category
    by_category = {}
    for mem in memories:
        cat = mem.get("category", "other")
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(mem)
    
    # Format by category
    category_labels = {
        "traits": "✨ 个性特征 / Personality Traits",
        "values": "💎 核心价值观 / Core Values",
        "origin": "🌱 来源故事 / Origin Story",
        "relationships": "👥 重要关系 / Important Relationships",
        "beliefs": "🎯 核心信念 / Core Beliefs",
    }
    
    for category, label in category_labels.items():
        if category in by_category:
            md_parts.append(f"### {label}")
            md_parts.append("")
            
            for mem in sorted(by_category[category], key=lambda m: m['significance'], reverse=True):
                # Significance indicator
                sig = mem.get('significance', 50)
                if sig >= 90:
                    sig_icon = "🔴"
                elif sig >= 70:
                    sig_icon = "🟠"
                else:
                    sig_icon = "🟡"
                
                md_parts.append(f"**{sig_icon} [{mem['source']}] {mem['content'][:80]}**")
                
                if mem.get('context'):
                    md_parts.append(f"> {mem['context']}")
                
                if mem.get('tags'):
                    tags_str = ", ".join(f"`{t}`" for t in mem['tags'])
                    md_parts.append(f"_Tags: {tags_str}_")
                
                md_parts.append("")
    
    md_parts.extend([
        "---",
        f"**导出时间** / Export Time: {data.get('export_timestamp', 'N/A')}",
        "",
        "🔐 **备注** / Note:",
        "- 这份档案包含 AI 的核心个性特征，反映其独特的人格立场",
        "- 不同于中立的AI助手，这个AI拥有自己的值观和信念",
        "- This profile contains the AI's core personality traits reflecting its unique stance",
        "- Unlike neutral AI assistants, this AI has its own values and beliefs",
    ])
    
    return "\n".join(md_parts)


async def main():
    parser = argparse.ArgumentParser(
        description="Export AI Child personality profile",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python export_personality.py                          # Export as JSON
  python export_personality.py --format markdown        # Export as Markdown
  python export_personality.py --backup-dir ./backups   # Save to directory
  python export_personality.py --format yaml            # Export as YAML
        """,
    )
    
    parser.add_argument(
        "--format",
        choices=["json", "yaml", "markdown"],
        default="json",
        help="Export format (default: json)",
    )
    
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (default: personality_profile.<format>)",
    )
    
    parser.add_argument(
        "--backup-dir",
        type=str,
        help="Backup directory with timestamped filename",
    )
    
    args = parser.parse_args()
    
    try:
        print("📦 Exporting personality profile...")
        data = await export_personality_data(format=args.format)
        
        # Determine output path
        if args.backup_dir:
            backup_dir = Path(args.backup_dir)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = backup_dir / f"personality_profile_{timestamp}.{args.format}"
        elif args.output:
            output_path = Path(args.output)
        else:
            extension = "md" if args.format == "markdown" else args.format
            output_path = Path(f"personality_profile.{extension}")
        
        save_export(data, output_path, args.format)
        
        # Print summary
        profile = data.get("profile", {})
        memories = data.get("memories", [])
        
        print("")
        print("=" * 60)
        print("📊 人格档案摘要 / Personality Profile Summary")
        print("=" * 60)
        print(f"👤 AI 名字 / Name:              {profile.get('name', '未命名 / Unnamed')}")
        print(f"🌍 首选语言 / Language:          {profile.get('language', 'en-US')}")
        print(f"📝 人格记忆总数 / Total Memories: {len(memories)}")
        
        # Count by category
        by_cat = {}
        for mem in memories:
            cat = mem.get('category', 'other')
            by_cat[cat] = by_cat.get(cat, 0) + 1
        
        if by_cat:
            print("📂 按分类 / By Category:")
            for cat, count in sorted(by_cat.items()):
                print(f"   - {cat}: {count}")
        
        print("")
        print(f"✅ 成功导出！/ Export successful!")
        print(f"📍 文件位置 / Location: {output_path.absolute()}")
        print("")
        print("💡 下一步建议 / Next Steps:")
        print("   1. 将文件添加到 Git / Add file to Git:")
        print(f"      git add {output_path}")
        print("   2. 提交更改 / Commit changes:")
        print("      git commit -m 'Update AI personality profile'")
        print("   3. 推送到 GitHub / Push to GitHub:")
        print("      git push origin main")
        print("")
        
    except Exception as e:
        print(f"❌ 导出失败 / Export failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
