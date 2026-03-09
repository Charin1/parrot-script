from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from backend.storage.vector_store import VectorStore

router = APIRouter(prefix='/api', tags=['search'])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator('query')
    @classmethod
    def normalize_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError('query cannot be empty')
        return cleaned


_vector_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore()
    return _vector_store


@router.post('/search')
async def semantic_search(body: SearchRequest) -> list[dict]:
    return get_vector_store().search(body.query, limit=body.limit)
