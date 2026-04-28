from __future__ import annotations

import logging
import json
import re
from typing import Any, List, Dict, Optional

from backend.config import settings
from backend.storage.vector_store import VectorStore
from backend.storage.repositories.segments import SegmentsRepository
from backend.llm.summarizer import MeetingSummarizer
from backend.llm.chunker import estimate_tokens

logger = logging.getLogger(__name__)

class ChatAgent:
    def __init__(self):
        self.vector_store = VectorStore()
        self.segments_repo = SegmentsRepository()
        self.summarizer = MeetingSummarizer()
        
        # Expert Tip: Reserve more buffer (800 tokens) for system instructions and long history
        # Local models perform significantly worse when the context window is near-full.
        self.max_context_tokens = settings.ollama_num_ctx - settings.summary_max_tokens - 1000

    async def chat(self, meeting_id: str, message: str, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Expert-level coordinator with robust error handling and signal-to-noise optimization.
        """
        history = history or []
        status_steps = []
        
        try:
            # 1. Intent Classification (Heuristic-first for speed/reliability)
            status_steps.append("Analyzing intent...")
            classification = await self._classify_intent(message, history)
            intent = classification.get("intent", "GENERAL")
            params = classification.get("params", {})
            
            logger.info(f"Chat | Meeting: {meeting_id} | Intent: {intent}")

            context_lines = []
            semantic_results = []
            source_type = intent.lower()

            # 2. Specialized Tool Routing
            status_steps.append(f"Retrieving {intent.lower()} context...")
            if intent == "TEMPORAL":
                context_lines = await self._tool_temporal(meeting_id, params)
            elif intent == "SPEAKER":
                context_lines = await self._tool_speaker(meeting_id, params, message)
            elif intent == "TASK":
                context_lines = await self._tool_task(meeting_id, params, message)
            else:
                # GENERAL / SEMANTIC
                semantic_results = self.vector_store.search(message, limit=15, meeting_id=meeting_id)
                context_lines = self._format_segments(semantic_results)

            # 3. Smart Context Injection (Hybrid RAG)
            # Expert Tip: Always include a "Recency Anchor" so the model isn't "lost in time"
            if intent != "TEMPORAL": # Temporal already has its window
                recent = await self._get_recent_context(meeting_id)
                # Deduplicate and merge
                existing_texts = set(context_lines)
                for r in recent:
                    if r not in existing_texts:
                        context_lines.append(r)

            # 4. Signal-to-Noise Filtering
            # Expert Tip: Remove segments that are too short to have meaning (save tokens + reduce noise)
            context_lines = [line for line in context_lines if len(line.split(": ", 1)[-1]) > 5]

            # 5. Context Window Management (Token Budgeting)
            context_text = "\n".join(context_lines)
            while estimate_tokens(context_text) > self.max_context_tokens and context_lines:
                context_lines.pop(0) # FIFO removal
                context_text = "\n".join(context_lines)

            # 6. Build Conversation History
            history_text = ""
            for turn in history[-5:]:
                role = "User" if turn['role'] == 'user' else "Parrot"
                history_text += f"{role}: {turn['content']}\n"

            # 7. Generate specialized prompt
            status_steps.append("Consulting local model...")
            prompt = self._build_specialized_prompt(intent, context_text, history_text, message, params)
            
            # 8. Call LLM
            response = await self.summarizer._call_ollama(prompt)
            
            return {
                "response": response,
                "context_found": len(context_lines) > 0,
                "sources": semantic_results if intent == "GENERAL" else [], 
                "intent": intent,
                "source_type": source_type,
                "status_steps": status_steps
            }

        except Exception as e:
            logger.exception(f"ChatAgent critical failure: {e}")
            # Expert Tip: Always return a user-friendly fallback instead of a 500
            return {
                "response": "I'm sorry, I'm having trouble processing that right now. It might be due to a large transcript or a local model timeout. Can you try rephrasing or asking about a shorter time window?",
                "context_found": False,
                "error": str(e)
            }

    async def _classify_intent(self, message: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        msg = message.lower()
        
        # 1. Temporal Heuristics
        if any(w in msg for w in ["last", "minutes", "mins", "beginning", "start", "just now", "recently"]):
            return {"intent": "TEMPORAL", "params": self._heuristic_time_parse(msg)}
            
        # 2. Task Heuristics
        if any(w in msg for w in ["task", "action", "next step", "todo", "decision", "decided", "assign"]):
            return {"intent": "TASK", "params": {}}

        # 3. Speaker Heuristics
        # Look for "Who" or names
        if msg.startswith("who") or "say" in msg or "think" in msg:
            # Simple capitalized name extraction
            names = re.findall(r"\b([A-Z][a-z]+)\b", message)
            if names and names[0] != "Parrot": # Ignore our own name
                return {"intent": "SPEAKER", "params": {"name": names[0]}}

        return {"intent": "GENERAL", "params": {}}

    async def _tool_temporal(self, meeting_id: str, params: Dict[str, Any]) -> List[str]:
        all_segments = await self.segments_repo.get_by_meeting(meeting_id)
        if not all_segments: return []
        
        max_time = all_segments[-1].get('end_time', 0)
        start_offset = 0
        end_offset = max_time

        t_type = params.get('type', 'last')
        t_val = params.get('value', 5)

        if t_type == 'last':
            start_offset = max(0, max_time - (t_val * 60))
        elif t_type == 'first':
            end_offset = min(max_time, t_val * 60)
            
        segments = await self.segments_repo.get_by_time_range(meeting_id, start_offset, end_offset)
        return self._format_segments_repo(segments)

    async def _tool_speaker(self, meeting_id: str, params: Dict[str, Any], query: str) -> List[str]:
        name = params.get("name")
        if not name:
            results = self.vector_store.search(query, limit=12, meeting_id=meeting_id)
            return self._format_segments(results)
            
        segments = await self.segments_repo.get_by_speaker(meeting_id, name)
        # Hybrid: Direct speaker segments + semantic search for context
        direct = self._format_segments_repo(segments)
        semantic = self._format_segments(self.vector_store.search(query, limit=8, meeting_id=meeting_id))
        
        # Merge and keep direct results at the end (more important context)
        return list(dict.fromkeys(semantic + direct))

    async def _tool_task(self, meeting_id: str, params: Dict[str, Any], query: str) -> List[str]:
        # Multi-query expansion for tasks
        task_query = f"action items tasks next steps decisions commitments {query}"
        results = self.vector_store.search(task_query, limit=15, meeting_id=meeting_id)
        return self._format_segments(results)

    async def _get_recent_context(self, meeting_id: str) -> List[str]:
        all_segments = await self.segments_repo.get_by_meeting(meeting_id)
        recent = all_segments[-10:] if all_segments else []
        return self._format_segments_repo(recent)

    def _format_segments(self, vector_results: List[Dict[str, Any]]) -> List[str]:
        lines = []
        for r in vector_results:
            meta = r.get('metadata', {})
            speaker = meta.get('speaker', 'Unknown')
            start = meta.get('start_time', 0)
            lines.append(f"[{start:.1f}s] {speaker}: {r['text']}")
        return lines

    def _format_segments_repo(self, repo_segments: List[Dict[str, Any]]) -> List[str]:
        lines = []
        for s in repo_segments:
            speaker = s.get('participant_name') or s.get('speaker', 'Unknown')
            start = s.get('start_time', 0)
            lines.append(f"[{start:.1f}s] {speaker}: {s['text']}")
        return lines

    def _heuristic_time_parse(self, msg: str) -> Dict[str, Any]:
        last_match = re.search(r"last\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+(min|minute)", msg)
        if last_match:
            val_str = last_match.group(1)
            mapping = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
            val = mapping.get(val_str, int(val_str) if val_str.isdigit() else 5)
            return {"type": "last", "value": val}
        if "beginning" in msg or "start" in msg:
            return {"type": "first", "value": 5}
        if "just now" in msg or "recently" in msg:
            return {"type": "last", "value": 3}
        return {"type": "last", "value": 5}

    def _build_specialized_prompt(self, intent: str, context: str, history: str, query: str, params: Dict[str, Any]) -> str:
        # Expert Tip: Use clear, visually distinct headers for the model.
        # This helps local models differentiate between your instructions and the data.
        
        system_base = "ROLE: You are 'Parrot Script', a precise local meeting intelligence agent."
        
        if intent == "SPEAKER":
            task_desc = f"GOAL: Answer questions about {params.get('name', 'the speaker')}. If they expressed an opinion, summarize it."
        elif intent == "TASK":
            task_desc = "GOAL: Extract commitments. Look for verbs like 'will', 'need to', 'shall', 'decided'."
        elif intent == "TEMPORAL":
            task_desc = "GOAL: Summarize the sequence of events in this specific time window."
        else:
            task_desc = "GOAL: Answer based on the semantic context provided."

        return f"""
{system_base}
{task_desc}

### CRITICAL CONSTRAINTS:
1. ONLY use the [MEETING DATA] and [HISTORY] below.
2. If the data is missing, say: "I don't have enough information in the transcript to answer that."
3. DO NOT hallucinate names or facts not listed.
4. Keep the answer under 4 sentences unless asked for detail.

### MEETING DATA (TRANSCRIPT SEGMENTS):
---
{context if context else "NO DATA FOUND."}
---

### CONVERSATION HISTORY:
{history if history else "START OF CONVERSATION."}

### USER QUERY:
{query}

### PARROT RESPONSE:
"""
