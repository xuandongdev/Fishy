import threading
from collections import defaultdict
from typing import DefaultDict, Dict, List


class ConversationManager:
    """In-memory conversation store keyed by session_id."""

    def __init__(self) -> None:
        self._store: DefaultDict[str, List[Dict[str, str]]] = defaultdict(list)
        self._lock = threading.Lock()

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        with self._lock:
            return list(self._store.get(session_id, []))

    def append_user_message(self, session_id: str, content: str) -> None:
        self._append_message(session_id, "user", content)

    def append_assistant_message(self, session_id: str, content: str) -> None:
        self._append_message(session_id, "assistant", content)

    def clear_history(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)

    def _append_message(self, session_id: str, role: str, content: str) -> None:
        cleaned = (content or "").strip()
        if not session_id or not cleaned:
            return
        with self._lock:
            self._store[session_id].append({"role": role, "content": cleaned})
