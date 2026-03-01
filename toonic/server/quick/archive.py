"""
Archive unpacking and watching utilities.
"""

from __future__ import annotations

import logging
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from toonic.server.quick.parsing import parse_source

if TYPE_CHECKING:
    from toonic.server.quick.builder import ConfigBuilder

logger = logging.getLogger("toonic.quick.archive")


_ZIP_EXTENSIONS = (".zip",)
_TAR_EXTENSIONS = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz")


def _is_zip_file(filename: str) -> bool:
    """Check if filename has zip extension."""
    return filename.lower().endswith(_ZIP_EXTENSIONS)


def _is_tar_file(filename: str) -> bool:
    """Check if filename has tar/tar.* extension."""
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in _TAR_EXTENSIONS)


def _extract_zip(archive_path: Path, out_dir: Path) -> None:
    """Extract zip archive to directory."""
    with zipfile.ZipFile(archive_path, "r") as zf:
        zf.extractall(out_dir)


def _extract_tar(archive_path: Path, out_dir: Path) -> None:
    """Extract tar archive to directory with security filter."""
    with tarfile.open(archive_path, "r:*") as tf:
        try:
            tf.extractall(out_dir, filter="data")
        except TypeError:
            tf.extractall(out_dir)


def unpack_archive(archive_path: str, output_dir: str | None = None) -> str:
    """Unpack an archive (zip/tar/tar.gz/...) and return the extraction directory."""
    ap = Path(archive_path)
    if not ap.exists():
        raise FileNotFoundError(f"Archive does not exist: {archive_path}")

    out_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="toonic-archive-"))
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        filename = ap.name

        if _is_zip_file(filename):
            _extract_zip(ap, out_dir)
            return str(out_dir)

        if _is_tar_file(filename):
            _extract_tar(ap, out_dir)
            return str(out_dir)

        raise ValueError(f"Unsupported archive format: {archive_path}")

    except Exception:
        if output_dir is None:
            shutil.rmtree(out_dir, ignore_errors=True)
        raise


def _should_include_file(p: Path) -> bool:
    """Determine if a file should be included as a source."""
    if not p.is_file():
        return False

    if p.name.startswith("."):
        return False

    try:
        if p.stat().st_size > 2_000_000:
            return False
    except OSError:
        return False

    return True


def _collect_files_from_directory(root: Path, max_files: int) -> list[Path]:
    """Collect files from directory up to max_files limit."""
    files = []
    for p in sorted(root.rglob("*")):
        if len(files) >= max_files:
            break
        if _should_include_file(p):
            files.append(p)
    return files


def watch_archive(
    archive_path: str,
    *,
    extract_dir: str | None = None,
    directory_category: str = "infra",
    include_files_as_sources: bool = False,
    max_files: int = 200,
) -> "ConfigBuilder":
    """Unpack an archive and return a ConfigBuilder watching its contents."""
    from toonic.server.quick.builder import ConfigBuilder
    from toonic.server.quick.runtime import watch

    extracted = unpack_archive(archive_path, output_dir=extract_dir)
    b = watch().add(f"dir:{extracted}")

    if directory_category and b._sources:
        b._sources[-1].category = directory_category

    if include_files_as_sources:
        root = Path(extracted)
        files = _collect_files_from_directory(root, max_files)
        for p in files:
            b.add(str(p))

    return b
