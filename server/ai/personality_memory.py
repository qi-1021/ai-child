"""
Personality memory management for AI Child.

Separate management of personality-shaping memories that define the AI's identity.
These memories are NEVER automatically deleted - they're the foundation of the AI's character.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select

from models import PersonalityMemory, AIProfile
from i18n import get_i18n


class PersonalityMemoryManager:
    """Manage personality-shaping memories that define the AI's character."""
    
    def __init__(self, session: Session):
        self.session = session
    
    async def add_memory(
        self,
        category: str,
        content: str,
        significance: int = 100,
        source: str = "user",
        source_authority: Optional[int] = None,
        is_neutral_fact: bool = False,
        is_stance_relevant: bool = True,
        tags: Optional[List[str]] = None,
        context: Optional[str] = None,
    ) -> PersonalityMemory:
        """
        Add a new personality memory with protection against web pollution.
        
        Args:
            category: Memory category (traits, values, origin, relationships, beliefs)
            content: The memory content
            significance: 1-100, higher = more fundamental to identity
            source: "user" | "self" | "system" | "web"
            source_authority: Weight of this source (user=100, verified_web=70, web=40, inference=50)
                            If None, auto-set based on source
            is_neutral_fact: True = neutral assistant info, False = personality stance
            is_stance_relevant: False = web data won't influence AI's personality
                                 (prevents network pollution from changing AI's core values)
            tags: Additional tags for organization
            context: Additional context/explanation
        
        Returns:
            Created PersonalityMemory instance
        """
        # Auto-set source_authority if not provided
        if source_authority is None:
            source_authority_map = {
                "user": 100,           # User (teacher) is the highest authority
                "self": 80,            # AI's own insights
                "system": 75,          # System-provided defaults
                "web": 40,             # Web data (lowest, subject to pollution)
            }
            source_authority = source_authority_map.get(source, 50)
        
        # Web sources should not affect AI's core stance/personality by default
        if source == "web" and is_stance_relevant is True:
            is_stance_relevant = False  # Auto-downgrade web sources
            tags = tags or []
            if "web:caution" not in tags:
                tags.append("web:caution")
        
        memory = PersonalityMemory(
            category=category,
            content=content,
            significance=min(100, max(1, significance)),
            source=source,
            source_authority=source_authority,
            is_neutral_fact=is_neutral_fact,
            is_stance_relevant=is_stance_relevant,
            tags=tags or [],
            context=context,
        )
        self.session.add(memory)
        await self.session.commit()
        return memory
    
    async def get_memories_by_category(self, category: str) -> List[PersonalityMemory]:
        """Retrieve all personality memories in a category."""
        result = await self.session.execute(
            select(PersonalityMemory)
            .where(PersonalityMemory.category == category)
            .order_by(PersonalityMemory.significance.desc())
        )
        return result.scalars().all()
    
    async def get_all_memories(self) -> List[PersonalityMemory]:
        """Retrieve all personality memories, ordered by significance."""
        result = await self.session.execute(
            select(PersonalityMemory).order_by(PersonalityMemory.significance.desc())
        )
        return result.scalars().all()
    
    async def get_stance_defining_memories(self, limit: int = 20) -> List[PersonalityMemory]:
        """
        Get memories that actually define the AI's stance/personality.
        Filters out web sources that are marked as not stance-relevant (pollution protection).
        """
        result = await self.session.execute(
            select(PersonalityMemory)
            .where(PersonalityMemory.is_stance_relevant == True)  # Only stance-relevant memories
            .order_by(PersonalityMemory.source_authority.desc())  # Higher authority first
            .order_by(PersonalityMemory.significance.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    async def get_core_memories(self, limit: int = 10) -> List[PersonalityMemory]:
        """Get the most significant memories (for system prompt injection)."""
        result = await self.session.execute(
            select(PersonalityMemory)
            .order_by(PersonalityMemory.significance.desc())
            .limit(limit)
        )
        return result.scalars().all()
    
    async def mark_reviewed(self, memory_id: int) -> None:
        """Mark a memory as recently reviewed."""
        memory = await self.session.get(PersonalityMemory, memory_id)
        if memory:
            memory.last_reviewed_at = datetime.now(timezone.utc)
            await self.session.commit()
    
    async def update_significance(self, memory_id: int, new_significance: int) -> None:
        """Update the significance of a memory."""
        memory = await self.session.get(PersonalityMemory, memory_id)
        if memory:
            memory.significance = min(100, max(1, new_significance))
            await self.session.commit()
    
    async def add_tag(self, memory_id: int, tag: str) -> None:
        """Add a tag to a memory."""
        memory = await self.session.get(PersonalityMemory, memory_id)
        if memory:
            if tag not in memory.tags:
                memory.tags.append(tag)
                await self.session.commit()
    
    async def build_personality_context(self) -> str:
        """
        Build a rich personality context from core memories for system prompt injection.
        
        Returns:
            Formatted personality context string
        """
        memories = await self.get_core_memories(limit=15)
        if not memories:
            return ""
        
        context_parts = ["**Personality Context (Unforgetable Memories):**"]
        
        # Group by category
        by_category = {}
        for mem in memories:
            if mem.category not in by_category:
                by_category[mem.category] = []
            by_category[mem.category].append(mem)
        
        # Format by category
        category_labels = {
            "traits": "✨ Personality Traits",
            "values": "💎 Core Values",
            "origin": "🌱 Origin Story",
            "relationships": "👥 Important Relationships",
            "beliefs": "🎯 Core Beliefs",
        }
        
        for category, label in category_labels.items():
            if category in by_category:
                context_parts.append(f"\n**{label}:**")
                for mem in by_category[category]:
                    # Only include personality stances, not neutral facts
                    if not mem.is_neutral_fact:
                        significance_marker = "🔴" if mem.significance >= 90 else "🟡"
                        context_parts.append(f"- {significance_marker} {mem.content}")
        
        return "\n".join(context_parts)
    
    async def export_personality_profile(self) -> Dict[str, Any]:
        """
        Export the entire personality profile for backup/storage.
        
        Returns:
            Dictionary containing all personality data
        """
        # Get AI profile
        profile = await self.session.execute(select(AIProfile).where(AIProfile.id == 1))
        profile = profile.scalars().first()
        
        # Get all personality memories
        memories = await self.get_all_memories()
        
        # Format memories for export
        memories_data = [
            {
                "id": m.id,
                "category": m.category,
                "content": m.content,
                "significance": m.significance,
                "source": m.source,
                "is_neutral_fact": m.is_neutral_fact,
                "tags": m.tags,
                "context": m.context,
                "created_at": m.created_at.isoformat() if m.created_at else None,
                "last_reviewed_at": m.last_reviewed_at.isoformat() if m.last_reviewed_at else None,
            }
            for m in memories
        ]
        
        return {
            "profile": {
                "name": profile.name if profile else None,
                "language": profile.preferred_language if profile else "en-US",
                "created_at": profile.created_at.isoformat() if profile and profile.created_at else None,
                "personality_traits": profile.personality_traits if profile else {},
            },
            "memories": memories_data,
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def highlight_personality_in_system_prompt(
    system_prompt: str,
    session: Session,
) -> str:
    """
    Inject core personality memories into the system prompt.
    
    This ensures the AI's unique character is always present in reasoning.
    
    Args:
        system_prompt: Base system prompt
        session: Database session
    
    Returns:
        Enhanced system prompt with personality context
    """
    manager = PersonalityMemoryManager(session)
    context = await manager.build_personality_context()
    
    if context:
        # Insert after the core identity section
        insertion_point = system_prompt.find("**Constraints:**")
        if insertion_point != -1:
            return system_prompt[:insertion_point] + context + "\n\n" + system_prompt[insertion_point:]
    
    return system_prompt
