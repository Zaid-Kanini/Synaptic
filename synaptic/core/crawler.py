"""Recursive file crawler with .gitignore-style blacklist filtering.

Uses ``pathlib`` for all file-system operations and ``pathspec`` for
glob-pattern matching against the configurable blacklist.
"""

from __future__ import annotations

import pathlib
from typing import Iterator

import pathspec
import structlog

from synaptic.config import settings

logger = structlog.get_logger(__name__)

# Map file extensions to language identifiers used by the parser factory.
EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
}


class FileCrawler:
    """Recursively walks a directory tree, yielding source files.

    Respects a configurable blacklist of glob patterns (similar to
    ``.gitignore``).  Files exceeding ``max_file_size_bytes`` are skipped.

    Args:
        root: The root directory to scan.
        blacklist: Optional list of glob patterns to exclude.  Falls back
            to :pyattr:`synaptic.config.Settings.default_blacklist`.
        max_file_size_bytes: Skip files larger than this.  Falls back to
            :pyattr:`synaptic.config.Settings.max_file_size_bytes`.
    """

    def __init__(
        self,
        root: pathlib.Path,
        blacklist: list[str] | None = None,
        max_file_size_bytes: int | None = None,
    ) -> None:
        self.root = root.resolve()
        self.blacklist = blacklist or settings.default_blacklist
        self.max_file_size_bytes = max_file_size_bytes or settings.max_file_size_bytes
        self._spec = pathspec.PathSpec.from_lines("gitwildmatch", self.blacklist)

    def _is_excluded(self, path: pathlib.Path) -> bool:
        """Check whether *path* matches any blacklist pattern.

        Args:
            path: Absolute path to test.

        Returns:
            ``True`` if the path should be skipped.
        """
        try:
            relative = path.relative_to(self.root)
        except ValueError:
            return False
        # pathspec expects forward-slash separated POSIX paths.
        posix = relative.as_posix()
        # For directories, append a trailing slash so directory patterns match.
        if path.is_dir():
            posix += "/"
        return self._spec.match_file(posix)

    def _is_supported(self, path: pathlib.Path) -> bool:
        """Return ``True`` if the file extension has a registered parser.

        Args:
            path: File path to check.
        """
        return path.suffix.lower() in EXTENSION_LANGUAGE_MAP

    def crawl(self) -> Iterator[pathlib.Path]:
        """Yield all supported source files under :pyattr:`root`.

        Directories matching the blacklist are pruned entirely so their
        children are never visited.

        Yields:
            Absolute ``pathlib.Path`` objects for each source file.
        """
        logger.info("crawl_started", root=str(self.root))
        file_count = 0

        for path in self._walk(self.root):
            file_count += 1
            yield path

        logger.info("crawl_finished", root=str(self.root), files_found=file_count)

    def _walk(self, directory: pathlib.Path) -> Iterator[pathlib.Path]:
        """Recursively walk *directory*, pruning excluded subtrees.

        Args:
            directory: Directory to walk.

        Yields:
            Source file paths.
        """
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            logger.warning("permission_denied", path=str(directory))
            return

        for entry in entries:
            if self._is_excluded(entry):
                logger.debug("excluded", path=str(entry))
                continue

            if entry.is_dir():
                yield from self._walk(entry)
            elif entry.is_file():
                if not self._is_supported(entry):
                    continue
                try:
                    size = entry.stat().st_size
                except OSError:
                    logger.warning("stat_failed", path=str(entry))
                    continue
                if size > self.max_file_size_bytes:
                    logger.warning(
                        "file_too_large",
                        path=str(entry),
                        size=size,
                        limit=self.max_file_size_bytes,
                    )
                    continue
                yield entry


def get_language_for_file(path: pathlib.Path) -> str | None:
    """Return the language identifier for a file based on its extension.

    Args:
        path: File path to inspect.

    Returns:
        Language string (e.g. ``"python"``) or ``None`` if unsupported.
    """
    return EXTENSION_LANGUAGE_MAP.get(path.suffix.lower())
