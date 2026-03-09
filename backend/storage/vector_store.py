from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import chromadb
from chromadb.utils import embedding_functions

from backend.config import settings


class VectorStore:
    def __init__(self):
        Path(settings.chroma_path).mkdir(parents=True, exist_ok=True)
        self.embedding_function = embedding_functions.DefaultEmbeddingFunction()
        self.client = chromadb.PersistentClient(path=settings.chroma_path)
        self.collection = self.client.get_or_create_collection(
            "meetings",
            embedding_function=self.embedding_function,
        )

    def embed_text(self, text: str) -> list[float]:
        return self.embedding_function([text])[0]

    async def add_meeting(self, meeting_id: str, transcript: str, summary: str) -> None:
        transcript_chunks = [chunk.strip() for chunk in transcript.split("\n\n") if chunk.strip()]
        if not transcript_chunks and transcript.strip():
            transcript_chunks = [transcript.strip()]

        ids: list[str] = []
        docs: list[str] = []
        metas: list[dict] = []

        for chunk in transcript_chunks:
            ids.append(str(uuid4()))
            docs.append(chunk)
            metas.append({"meeting_id": meeting_id, "type": "transcript"})

        if summary.strip():
            ids.append(str(uuid4()))
            docs.append(summary.strip())
            metas.append({"meeting_id": meeting_id, "type": "summary"})

        if docs:
            self.collection.upsert(ids=ids, documents=docs, metadatas=metas)

    def search(self, query: str, limit: int = 10) -> list[dict]:
        if not query.strip():
            return []

        results = self.collection.query(query_texts=[query], n_results=limit)
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        output: list[dict] = []
        for idx, text in enumerate(documents):
            metadata = metadatas[idx] if idx < len(metadatas) else {}
            distance = float(distances[idx]) if idx < len(distances) else 0.0
            output.append(
                {
                    "meeting_id": metadata.get("meeting_id", ""),
                    "text": text,
                    "score": 1.0 / (1.0 + distance),
                }
            )

        return output
