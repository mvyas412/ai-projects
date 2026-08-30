import pytest

from backend.app.storage.local import LocalFileStorage


def test_local_storage_round_trip_and_delete(tmp_path) -> None:
    storage = LocalFileStorage(tmp_path / "objects")

    storage.put("workspace/document/original.pdf", b"pdf-content")

    assert storage.exists("workspace/document/original.pdf")
    assert storage.read("workspace/document/original.pdf") == b"pdf-content"
    storage.delete("workspace/document/original.pdf")
    assert not storage.exists("workspace/document/original.pdf")


@pytest.mark.parametrize("key", ["", "/absolute.pdf", "../escape.pdf", "a/../../escape", "a\\b"])
def test_local_storage_rejects_unsafe_keys(tmp_path, key: str) -> None:
    storage = LocalFileStorage(tmp_path / "objects")

    with pytest.raises(ValueError):
        storage.put(key, b"unsafe")
