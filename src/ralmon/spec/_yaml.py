"""Strict and bounded YAML reading for the loaders of ``ralmon.spec``.

The configuration files are read as plain data: ``yaml.SafeLoader`` only (no object construction),
a size limit before parsing, no anchors or aliases (no expansion bomb), no merge keys, no duplicate
keys. Every failure is raised as the error class the caller passes, never as a raw ``OSError``,
``UnicodeDecodeError``, ``yaml.YAMLError`` or ``RecursionError``.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Hashable
from pathlib import Path
from typing import Any

import yaml

from ralmon.spec._text import describe, show, show_path, type_name

# algorithmic: upper bound on a configuration file (1 MiB); the real files are a few kilobytes
MAX_FILE_BYTES: int = 1_048_576

_MERGE_TAG = "tag:yaml.org,2002:merge"


class _StrictLoader(yaml.SafeLoader):
    """Safe loader that refuses anchors, aliases, merge keys and repeated keys."""

    def compose_node(self, parent: yaml.Node | None, index: object) -> yaml.Node | None:
        event = self.peek_event()  # type: ignore[no-untyped-call]
        if getattr(event, "anchor", None) is not None:
            raise yaml.composer.ComposerError(
                None, None, "anchors and aliases are not allowed", event.start_mark
            )
        return super().compose_node(parent, index)  # type: ignore[arg-type]

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[Hashable, Any]:
        seen: set[Hashable] = set()
        for key_node, _value_node in node.value:
            if key_node.tag == _MERGE_TAG:
                raise yaml.constructor.ConstructorError(
                    None, None, "merge keys are not allowed", key_node.start_mark
                )
            key = self.construct_object(key_node, deep=deep)
            if isinstance(key, Hashable):
                if key in seen:
                    raise yaml.constructor.ConstructorError(
                        None,
                        None,
                        f"duplicate key {show(key)} in a mapping",
                        key_node.start_mark,
                    )
                seen.add(key)
        return super().construct_mapping(node, deep=deep)


def coerce_path(path: object, error: type[Exception], what: str) -> Path:
    """``path`` as a ``Path``; a value that is not a ``str`` or ``os.PathLike`` of text is refused."""
    if isinstance(path, bool) or not isinstance(path, (str, os.PathLike)):
        raise error(
            f"{what}: the path must be a str or an os.PathLike, got {show(path)}"
        )
    try:
        raw = os.fspath(path)
    except Exception as exc:
        raise error(
            f"{what}: the path cannot be converted to text ({describe(exc)})"
        ) from exc
    if not isinstance(raw, str):
        raise error(f"{what}: the path must be text, not {type_name(raw)}")
    return Path(raw)


def read_limited_bytes(path: Path, error: type[Exception], what: str) -> bytes:
    """The bytes of the regular file at ``path``, refused if it is larger than ``MAX_FILE_BYTES``.

    The file is opened without blocking and the kind of file is checked on the open descriptor, not on
    the path, so that a named pipe, a device or a directory is refused with ``error`` (a plain
    ``open`` of a named pipe with no writer blocks for ever) and there is no race between a check of
    the path and the open.
    """
    limit = MAX_FILE_BYTES
    shown = show_path(path)
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except (OSError, ValueError) as exc:
        reason = (
            exc.strerror if isinstance(exc, OSError) and exc.strerror else describe(exc)
        )
        raise error(f"{what}: cannot read {shown}: {reason}") from exc
    try:
        is_regular = stat.S_ISREG(os.fstat(descriptor).st_mode)
    except OSError as exc:
        os.close(descriptor)
        raise error(f"{what}: cannot read {shown}: {describe(exc)}") from exc
    if not is_regular:
        os.close(descriptor)
        raise error(f"{what}: {shown} is not a regular file")
    try:
        with open(
            descriptor, "rb"
        ) as handle:  # takes over the descriptor and closes it
            data = handle.read(limit + 1)
    except (OSError, ValueError) as exc:
        raise error(f"{what}: cannot read {shown}: {describe(exc)}") from exc
    if len(data) > limit:
        raise error(f"{what}: {shown} is larger than {limit} bytes")
    return data


def parse_yaml_bytes(data: bytes, error: type[Exception], where: str) -> object:
    """Parse the single YAML document in ``data`` (UTF-8) with the strict safe loader."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise error(f"{where}: the file is not valid UTF-8 ({describe(exc)})") from exc
    try:
        return yaml.load(text, Loader=_StrictLoader)
    except yaml.YAMLError as exc:
        raise error(f"{where}: invalid YAML ({describe(exc)})") from exc
    except RecursionError as exc:
        raise error(f"{where}: the YAML is nested too deeply") from exc
    except Exception as exc:  # an impossible date, an oversized number, ...
        raise error(f"{where}: invalid YAML content ({describe(exc)})") from exc
