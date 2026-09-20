from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.phase10_capacity_snapshot import (
    _backup_age_hours,
    _cpu_counters,
    _memory_values,
    _sustained_minutes,
)


def test_linux_cpu_and_memory_parsers() -> None:
    idle, total = _cpu_counters("cpu  10 2 3 40 5 0 0 0 0 0\n")
    assert idle == 45
    assert total == 60
    assert _memory_values("MemTotal: 1000 kB\nMemAvailable: 250 kB\n") == {
        "MemTotal": 1000,
        "MemAvailable": 250,
    }


def test_backup_age_uses_latest_encrypted_generation(tmp_path: Path) -> None:
    older = tmp_path / "older.age"
    newer = tmp_path / "newer.age"
    older.write_bytes(b"old")
    newer.write_bytes(b"new")
    now = datetime.now(UTC)
    older_time = (now - timedelta(hours=10)).timestamp()
    newer_time = (now - timedelta(hours=2)).timestamp()
    older.touch()
    newer.touch()
    import os

    os.utime(older, (older_time, older_time))
    os.utime(newer, (newer_time, newer_time))
    assert 1.9 <= _backup_age_hours(tmp_path, now) <= 2.1


def test_sustained_threshold_state_resets(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    start = datetime(2026, 9, 20, 10, tzinfo=UTC)
    assert _sustained_minutes(state, start, True) == 0
    assert _sustained_minutes(state, start + timedelta(minutes=16), True) == 16
    assert _sustained_minutes(state, start + timedelta(minutes=17), False) == 0
