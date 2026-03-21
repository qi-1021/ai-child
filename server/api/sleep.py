"""
Sleep state and event endpoints.

GET  /sleep/state           – current sleep state (is_sleeping, schedule)
GET  /sleep/events/pending  – unconsumed sleep/wake notifications
POST /sleep/events/{id}/consumed – mark an event as delivered (by bot)
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai.sleep import get_sleep_state
from models import SleepEvent, get_session

router = APIRouter(prefix="/sleep", tags=["sleep"])


class SleepEventOut(BaseModel):
    id: int
    event_type: str
    message: str | None
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/state")
async def sleep_state():
    """Return whether the AI child is currently sleeping and its schedule."""
    return await get_sleep_state()


@router.get("/events/pending", response_model=List[SleepEventOut])
async def pending_events(session: AsyncSession = Depends(get_session)):
    """Return all sleep/wake events that the bot has not yet delivered."""
    result = await session.execute(
        select(SleepEvent)
        .where(SleepEvent.consumed == False)
        .order_by(SleepEvent.created_at)
    )
    events = result.scalars().all()
    return [
        SleepEventOut(
            id=e.id,
            event_type=e.event_type,
            message=e.message,
            created_at=e.created_at.isoformat(),
        )
        for e in events
    ]


@router.post("/events/{event_id}/consumed")
async def mark_consumed(
    event_id: int, session: AsyncSession = Depends(get_session)
):
    """Mark a sleep event as consumed (bot has sent it to all chats)."""
    result = await session.execute(
        select(SleepEvent).where(SleepEvent.id == event_id)
    )
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Sleep event not found")
    event.consumed = True
    await session.commit()
    return {"ok": True}
