from __future__ import annotations

import fnmatch
import re
from pathlib import PurePosixPath
from typing import Any


DANGEROUS_COMMAND_PATTERNS = [
    "rm",
    "rm-*",
    "rm/*",
    "rmdir",
    "del",
    "erase",
    "remove-item",
    "format",
    "mkfs",
    "shutdown",
    "reboot",
    "kill",
    "taskkill",
]


class PermissionGuard:
    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.dir_patterns = [str(item) for item in config.get("dir", {}).get("deny", [])]
        self.command_patterns = [
            str(item) for item in config.get("command", {}).get("deny", [])
        ]
        self.file_patterns = [str(item) for item in config.get("file", {}).get("deny", [])]

    def is_denied_command(self, command_text: str) -> bool:
        normalized = command_text.casefold()
        tokens = re.findall(r"[A-Za-z0-9_.:/\\*-]+", normalized)
        patterns = [*self.command_patterns, *DANGEROUS_COMMAND_PATTERNS]
        for pattern in patterns:
            p = pattern.casefold()
            if any(fnmatch.fnmatch(token, p) for token in tokens):
                return True
            if fnmatch.fnmatch(normalized, p) or p in normalized.split():
                return True
        return False

    def is_denied_path(self, path_text: str, operation: str = "read") -> bool:
        path = self._normalize_path(path_text)
        filename = PurePosixPath(path).name
        lowered = path.casefold()
        lowered_name = filename.casefold()

        for pattern in self.file_patterns:
            p = self._normalize_pattern(pattern)
            if fnmatch.fnmatch(lowered_name, p) or fnmatch.fnmatch(lowered, p):
                return True

        for pattern in self.dir_patterns:
            p = self._normalize_pattern(pattern).strip("/")
            if not p:
                continue
            if fnmatch.fnmatch(lowered, p) or fnmatch.fnmatch(lowered, f"*{p}*"):
                return True
            parts = lowered.split("/")
            if p in parts or any(fnmatch.fnmatch(part, p) for part in parts):
                return True
        return False

    @staticmethod
    def _normalize_path(path_text: str) -> str:
        return path_text.replace("\\", "/").strip().lstrip("./").casefold()

    @classmethod
    def _normalize_pattern(cls, pattern: str) -> str:
        return pattern.replace("\\", "/").strip().lstrip("./").casefold()
