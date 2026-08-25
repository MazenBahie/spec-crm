"""Attachment storage behind a narrow interface.

Only ``LocalFileStorage`` exists today; object storage (S3 et al.) is out of
scope but should slot in behind the same three methods.
"""

from __future__ import annotations

import logging
import re
import shutil
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.config import settings
from app.services.errors import PayloadTooLarge

logger = logging.getLogger(__name__)

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_CHUNK = 1024 * 1024


def sanitise_filename(filename: str) -> str:
    """Reduce an arbitrary upload name to a safe single path segment.

    Strips directory separators, control characters, and leading dots. The
    original is preserved verbatim in ``attachments.filename`` for display.
    """
    name = unicodedata.normalize("NFKD", filename or "")
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(ch for ch in name if ch.isprintable())
    name = _UNSAFE.sub("_", name).strip("._")
    return name[:120] or "upload"


class Storage(Protocol):
    def save(self, stream: BinaryIO, *, filename: str) -> tuple[str, int]: ...
    def open(self, storage_path: str) -> BinaryIO: ...
    def delete(self, storage_path: str) -> None: ...


class LocalFileStorage:
    """Filesystem-backed storage rooted at ``settings.attachments_dir``."""

    def __init__(self, root: str | Path | None = None, max_bytes: int | None = None) -> None:
        self.root = Path(root if root is not None else settings.attachments_dir)
        self.max_bytes = max_bytes if max_bytes is not None else settings.max_upload_bytes

    def _resolve(self, storage_path: str) -> Path:
        """Resolve a stored relative path, refusing anything outside the root."""
        root = self.root.resolve()
        target = (root / storage_path).resolve()
        if target != root and root not in target.parents:
            raise ValueError(f"storage path escapes root: {storage_path!r}")
        return target

    def save(self, stream: BinaryIO, *, filename: str) -> tuple[str, int]:
        """Stream ``stream`` to disk, returning ``(storage_path, size_bytes)``.

        The file is copied in chunks — never fully buffered in memory — and the
        partial write is removed if the size limit is exceeded.
        """
        now = datetime.now(timezone.utc)
        relative = Path(f"{now:%Y}") / f"{now:%m}" / f"{uuid.uuid4()}_{sanitise_filename(filename)}"
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)

        size = 0
        # TODO: virus scan the stream before/while it lands on disk.
        try:
            with target.open("wb") as fh:
                while chunk := stream.read(_CHUNK):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise PayloadTooLarge(
                            f"upload exceeds {self.max_bytes} bytes"
                        )
                    fh.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise

        return relative.as_posix(), size

    def open(self, storage_path: str) -> BinaryIO:
        return self._resolve(storage_path).open("rb")

    def delete(self, storage_path: str) -> None:
        """Best-effort removal; missing files are not an error."""
        try:
            self._resolve(storage_path).unlink(missing_ok=True)
        except (OSError, ValueError) as exc:
            logger.warning("failed to delete attachment %s: %s", storage_path, exc)

    def purge_root(self) -> None:
        """Remove the whole tree (test helper)."""
        shutil.rmtree(self.root, ignore_errors=True)


def get_storage() -> LocalFileStorage:
    """FastAPI dependency. Reads settings on each call so tests can override."""
    return LocalFileStorage()
