from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_migration_history_has_document_library_head() -> None:
    config = Config(PROJECT_ROOT / "alembic.ini")
    scripts = ScriptDirectory.from_config(config)

    assert scripts.get_heads() == ["20260830_0005"]
    baseline = scripts.get_revision("20260829_0001")
    assert baseline is not None
    assert baseline.down_revision is None
    identity_workspaces = scripts.get_revision("20260829_0002")
    assert identity_workspaces is not None
    assert identity_workspaces.down_revision == "20260829_0001"
    document_library = scripts.get_revision("20260830_0003")
    assert document_library is not None
    assert document_library.down_revision == "20260829_0002"
    conversations = scripts.get_revision("20260830_0004")
    assert conversations is not None
    assert conversations.down_revision == "20260830_0003"
    audit_events = scripts.get_revision("20260830_0005")
    assert audit_events is not None
    assert audit_events.down_revision == "20260830_0004"
