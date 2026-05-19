"""
基于 JSONL 文件的轻量长期记忆存储。

它的实现足够直观，
既方便面试讲解，也能展示真实的长期记忆流程。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

from config.settings import settings
from models.schemas import MemoryEntry, TravelPlanState
from services.qwen_client import QwenClient

SUMMARY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You summarize a travel planning session into stable user preferences. "
            "Return compact JSON with a single key named summary.",
        ),
        (
            "human",
            "User preferences:\n{preferences}\n\n"
            "Selected destination:\n{destination}\n\n"
            "Budget notes:\n{budget}\n\n"
            "Create a short memory summary that helps a future travel planning session.",
        ),
    ]
)


class JsonMemoryStore:
    """Persist and retrieve long-term memory entries."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or settings.MEMORY_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path_for_user(self, user_id: str) -> Path:
        return self.base_dir / f"{user_id}.jsonl"

    async def load_user_context(self, user_id: str, limit: int = 5) -> list[MemoryEntry]:
        """Load the latest memory entries for a user."""

        path = self._path_for_user(user_id)
        if not path.exists():
            return []
        return await asyncio.to_thread(self._read_entries, path, limit)

    async def save_entry(self, entry: MemoryEntry) -> None:
        """Append one memory entry."""

        await asyncio.to_thread(self._append_entry, self._path_for_user(entry.user_id), entry)

    async def summarize_and_save(
        self,
        *,
        state: TravelPlanState,
        qwen: QwenClient | None = None,
    ) -> MemoryEntry | None:
        """Persist a compact memory summary for the finished plan."""

        prefs = state.preferences
        if prefs is None or not prefs.enable_long_term_memory or not settings.ENABLE_LONG_TERM_MEMORY:
            return None

        destination = state.selected_destination.city if state.selected_destination else ""
        budget = state.budget_breakdown.model_dump_json() if state.budget_breakdown else "{}"
        summary = self._fallback_summary(state)
        if qwen and state.selected_destination:
            try:
                data = await qwen.complete_json(
                    SUMMARY_PROMPT,
                    {
                        "preferences": prefs.model_dump_json(),
                        "destination": destination,
                        "budget": budget,
                    },
                )
                summary = str(data.get("summary", summary))
            except Exception:
                summary = self._fallback_summary(state)

        entry = MemoryEntry(
            user_id=prefs.user_id,
            session_id=prefs.session_id,
            summary=summary,
            preferences_snapshot=prefs.model_dump(),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await self.save_entry(entry)
        return entry

    @staticmethod
    def _append_entry(path: Path, entry: MemoryEntry) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.model_dump(mode="json"), ensure_ascii=False) + "\n")

    @staticmethod
    def _read_entries(path: Path, limit: int) -> list[MemoryEntry]:
        entries: list[MemoryEntry] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                entries.append(MemoryEntry(**json.loads(line)))
        return entries[-limit:]

    @staticmethod
    def _fallback_summary(state: TravelPlanState) -> str:
        prefs = state.preferences
        if prefs is None:
            return "No stable preferences captured."
        destination = state.selected_destination.city if state.selected_destination else "unknown destination"
        return (
            f"User prefers {prefs.travel_style.value} trips from {prefs.departure_city} with "
            f"budget {prefs.budget:.0f}, interests {', '.join(prefs.interests) or 'not specified'}, "
            f"last selected {destination}."
        )
