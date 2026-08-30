from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile


class LocalFileStorage:
    """Temporary path-safe adapter retained until Phase 3 object storage lands."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, content: bytes) -> None:
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with NamedTemporaryFile(
                dir=destination.parent, prefix=".upload-", delete=False
            ) as file:
                file.write(content)
                temporary = Path(file.name)
            temporary.replace(destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._resolve(key).is_file()

    def delete(self, key: str) -> None:
        self._resolve(key).unlink(missing_ok=True)

    def _resolve(self, key: str) -> Path:
        if not key or "\\" in key:
            raise ValueError("Storage key must be a non-empty POSIX-style relative path")
        relative = PurePosixPath(key)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise ValueError("Storage key must not escape the configured root")
        destination = self._root.joinpath(*relative.parts).resolve()
        if not destination.is_relative_to(self._root):
            raise ValueError("Storage key must not escape the configured root")
        return destination
