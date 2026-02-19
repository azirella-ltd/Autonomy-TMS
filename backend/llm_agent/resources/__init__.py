"""Resource package for Autonomy Simulation Strategist assets."""

from importlib import resources as _resources
from pathlib import Path as _Path
from typing import Iterator as _Iterator

__all__ = ["iter_files"]


def iter_files() -> _Iterator[_Path]:
    """Yield filesystem paths to packaged asset files."""

    package_root = _resources.files(__name__)
    with _resources.as_file(package_root) as resolved_root:
        root_path = _Path(resolved_root)
        for file_path in root_path.rglob("*"):
            if file_path.is_file() and file_path.name != "__init__.py":
                yield file_path
