#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import AI Child personality profile from backup.

Usage:
    python import_personality.py personality_profile.json                 # Import from JSON
    python import_personality.py personality_profile.yaml --format yaml   # Import from YAML
    python import_personality.py backups/ --merge                         # Merge with existing
"""

import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
import argparse

# Add server to path
server_path = Path(__file__).parent / "server"
sys.path.insert(0, str(server_path))

from sqlalchemy import select
from models import PersonalityMemory, AIProfile, init_db, async_session
from ai.personality_memory import PersonalityMemoryManager


async def import_personality_data(
    file_path: Path,
    format: str = "json",
    merge: bool = False,
) -> None:
    """Import personality profile into database."""
    
    if not file_path.exists():
        print(f"❌ 文件不存在 / File not found: {file_path}")
        sys.exit(1)
    
    # Load data
    print(f"📖 正在读取... / Reading: {file_path}")
    
    if format == "json":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    elif format == "yaml":
        try:
            import yaml
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except ImportError:
            print("❌ YAML format requires 'pip install pyyaml'")
            sys.exit(1)
    else:
        print(f"❌ 不支持的格式 / Unsupported format: {format}")
        sys.exit(1)
    
    # Import into database
    async with async_session() as session:
        await init_db()
        
        # Get or create AI profile
        profile_data = data.get("profile", {})
        profile = await session.execute(select(AIProfile).where(AIProfile.id == 1))
        profile = profile.scalars().first()
        
        if not profile:
            profile = AIProfile(id=1)
            session.add(profile)
        
        # Update profile
        if profile_data.get("name"):
            profile.name = profile_data["name"]
        
        if profile_data.get("language"):
            profile.preferred_language = profile_data["language"]
        
        if profile_data.get("personality_traits"):
            profile.personality_traits = profile_data["personality_traits"]
        
        await session.commit()
        
        # If not merging, clear existing memories
        if not merge:
            print("🗑️  清空现有记忆... / Clearing existing memories...")
            await session.execute(PersonalityMemory.__delete__())
            await session.commit()
        
        # Import memories
        manager = PersonalityMemoryManager(session)
        memories_data = data.get("memories", [])
        
        print(f"📝 正在导入 {len(memories_data)} 条记忆... / Importing {len(memories_data)} memories...")
        
        imported_count = 0
        for mem_data in memories_data:
            existing = await session.execute(
                select(PersonalityMemory).where(
                    (PersonalityMemory.category == mem_data.get("category"))
                    & (PersonalityMemory.content == mem_data.get("content"))
                )
            )
            
            if existing.scalars().first() and merge:
                # Skip if already exists in merge mode
                continue
            
            memory = await manager.add_memory(
                category=mem_data.get("category", "traits"),
                content=mem_data.get("content", ""),
                significance=mem_data.get("significance", 100),
                source=mem_data.get("source", "user"),
                is_neutral_fact=mem_data.get("is_neutral_fact", False),
                tags=mem_data.get("tags", []),
                context=mem_data.get("context"),
            )
            imported_count += 1
        
        print(f"✅ 导入完成！/ Import complete!")
        print(f"   - AI 名字 / Name: {profile.name or '(未设置)'}")
        print(f"   - 语言 / Language: {profile.preferred_language}")
        print(f"   - 导入记忆 / Memories imported: {imported_count}")


async def main():
    parser = argparse.ArgumentParser(
        description="Import AI Child personality profile from backup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python import_personality.py personality_profile.json
  python import_personality.py backup_20240321.yaml --format yaml
  python import_personality.py old_profile.json --merge        # Merge with existing
        """,
    )
    
    parser.add_argument(
        "file_path",
        type=str,
        help="Path to personality profile file (JSON/YAML)",
    )
    
    parser.add_argument(
        "--format",
        choices=["json", "yaml", "markdown"],
        default="json",
        help="File format (default: auto-detect from extension)",
    )
    
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge with existing memories instead of replacing",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview import without modifying database",
    )
    
    args = parser.parse_args()
    
    file_path = Path(args.file_path)
    
    # Auto-detect format from extension if not specified
    if args.format == "json":
        if file_path.suffix == ".yaml" or file_path.suffix == ".yml":
            args.format = "yaml"
        elif file_path.suffix == ".md":
            args.format = "markdown"
    
    if args.format == "markdown":
        print("❌ Markdown format is export-only (use JSON/YAML to import)")
        sys.exit(1)
    
    if args.dry_run:
        print("🔍 干运行模式 / Dry-run mode - Nothing will be modified")
        print("")
        
        if args.format == "json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            try:
                import yaml
                with open(file_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except ImportError:
                print("❌ YAML format requires 'pip install pyyaml'")
                sys.exit(1)
        
        profile = data.get("profile", {})
        memories = data.get("memories", [])
        
        print("📊 将导入以下数据 / Will import:")
        print(f"  - AI 名字 / Name: {profile.get('name', '(未设置)')}")
        print(f"  - 语言 / Language: {profile.get('language', 'en-US')}")
        print(f"  - 记忆总数 / Total memories: {len(memories)}")
        
        # Show first few memories
        if memories:
            print("\n  首批记忆样本 / Sample memories:")
            for mem in memories[:3]:
                print(f"    - [{mem.get('category')}] {mem.get('content', '')[:50]}")
            if len(memories) > 3:
                print(f"    ... 和 {len(memories) - 3} 条更多")
        
        return
    
    try:
        await import_personality_data(
            file_path=file_path,
            format=args.format,
            merge=args.merge,
        )
        
        mode = "Merged" if args.merge else "Replaced"
        print(f"\n💾 {mode} AI personality data successfully!")
        print("🚀 重启服务器来加载新的人格档案")
        print("🚀 Restart the server to load the new personality profile")
        
    except Exception as e:
        print(f"❌ 导入失败 / Import failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
