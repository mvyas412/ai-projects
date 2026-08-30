from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_migration_history_has_one_baseline_head() -> None:
    config = Config(PROJECT_ROOT / "alembic.ini")
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["20260829_0001"]
    baseline = scripts.get_revision("20260829_0001")
    assert baseline is not None
    assert baseline.down_revision is None
