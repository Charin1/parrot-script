from backend.api.routes.meetings import router as meetings_router
from backend.api.routes.search import router as search_router
from backend.api.routes.summaries import router as summaries_router
from backend.api.routes.transcripts import router as transcripts_router

__all__ = [
    "meetings_router",
    "transcripts_router",
    "summaries_router",
    "search_router",
]
