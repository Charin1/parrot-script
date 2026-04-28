from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.llm.agent_service import ChatAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meetings/{meeting_id}/agent", tags=["agent"])

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []

@router.post("/chat")
async def chat_with_meeting(meeting_id: str, body: ChatRequest) -> dict[str, Any]:
    """
    Advanced RAG-based chat with history and context optimization.
    """
    try:
        agent = ChatAgent()
        # Convert Pydantic models to dicts for the service
        history_dicts = [m.model_dump() for m in body.history]
        
        result = await agent.chat(
            meeting_id=meeting_id,
            message=body.message,
            history=history_dicts
        )
        
        return result

    except Exception as exc:
        logger.exception("Agent chat failed for meeting %s: %s", meeting_id, exc)
        raise HTTPException(status_code=500, detail="The AI agent encountered an error processing your request.")
