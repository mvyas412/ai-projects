from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

_SAFE_PROCESS = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class ProcessHealth:
    """Persist a secret-free local heartbeat for container and operator probes."""

    def __init__(self, directory: Path, process_name: str) -> None:
        if _SAFE_PROCESS.fullmatch(process_name) is None:
            raise ValueError("Invalid process health name")
        self.path = directory / f"{process_name}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._payload: dict[str, Any] = {
            "process": process_name,
            "state": "starting",
            "ready": False,
            "in_flight": 0,
            "counters": {},
        }
        self.write()

    def update(self, *, state: str, ready: bool, in_flight: int = 0) -> None:
        self._payload.update(state=state, ready=ready, in_flight=max(0, in_flight))
        self.write()

    def increment(self, counter: str) -> None:
        counters = self._payload["counters"]
        counters[counter] = int(counters.get(counter, 0)) + 1
        self.write()

    def write(self) -> None:
        payload = {**self._payload, "updated_at": datetime.now(UTC).isoformat()}
        temporary: str | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}-",
                delete=False,
            ) as file:
                temporary = file.name
                json.dump(payload, file, sort_keys=True, separators=(",", ":"))
            os.replace(temporary, self.path)
            temporary = None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)


def health_is_ready(path: Path, *, max_age: timedelta) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        updated_at = datetime.fromisoformat(str(payload["updated_at"]))
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return bool(payload["ready"]) and datetime.now(UTC) - updated_at <= max_age
    except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False
