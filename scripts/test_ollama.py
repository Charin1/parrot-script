#!/usr/bin/env python3
from __future__ import annotations

import asyncio

import httpx

from backend.config import settings


async def main() -> None:
    base_url = settings.ollama_base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
        tags = await client.get(f"{base_url}/api/tags")
        tags.raise_for_status()

        print("Ollama is running. Available models:")
        models = tags.json().get("models", [])
        for model in models:
            print(f"  - {model.get('name')}")

        resp = await client.post(
            f"{base_url}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": "Summarize: Team agreed to ship the API by Friday. Alice owns tests.",
                "stream": False,
            },
        )
        resp.raise_for_status()
        print("\nSample response:\n")
        print(resp.json().get("response", "<no response>"))


if __name__ == "__main__":
    asyncio.run(main())
