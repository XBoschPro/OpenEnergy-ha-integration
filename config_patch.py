"""
configuration.yaml patcher.

Adds/updates:
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 127.0.0.1
    - ::1
    - 172.30.32.0/24

Also adds a short comment before the http block explaining it's required for OpenEnergy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import re
from typing import Optional

from homeassistant.core import HomeAssistant


class ConfigPatchError(Exception):
    """Raised when configuration.yaml cannot be patched."""


def _ensure_list(v: Any) -> List[Any]:
    """Ensure a value is a list."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def patch_configuration_yaml(hass: HomeAssistant) -> bool:
    """
    Patch configuration.yaml and return True if changes were made.

    Uses ruamel.yaml when available to preserve YAML comments and formatting.
    Falls back to a minimal text append if YAML parsing fails.
    """
    cfg_path = Path(hass.config.path("configuration.yaml"))
    if not cfg_path.exists():
        raise ConfigPatchError("configuration.yaml not found")

    raw = cfg_path.read_text(encoding="utf-8")

    # Try ruamel.yaml first (present in HA)
    try:
        from ruamel.yaml import YAML  # type: ignore

        yaml = YAML()
        yaml.preserve_quotes = True

        data = yaml.load(raw) or {}
        if not isinstance(data, dict):
            raise ConfigPatchError("configuration.yaml root is not a mapping")

        http = data.get("http") or {}
        if not isinstance(http, dict):
            http = {}

        changed = False

        if http.get("use_x_forwarded_for") is not True:
            http["use_x_forwarded_for"] = True
            changed = True

        tp = _ensure_list(http.get("trusted_proxies"))
        wanted = ["127.0.0.1", "::1", "172.30.32.0/24"]
        for w in wanted:
            if w not in tp:
                tp.append(w)
                changed = True
        http["trusted_proxies"] = tp

        if data.get("http") != http:
            data["http"] = http
            changed = True

        # Comment before http block
        try:
            data.yaml_set_comment_before_after_key(
                "http",
                before=(
                    "OpenEnergy: required for secure external access through the OpenEnergy tunnel (FRP).\n"
                    "Do not remove unless you know what you are doing.\n"
                ),
            )
        except Exception:
            # Commenting is best-effort only
            pass

        if not changed:
            return False

        from io import StringIO
        buf = StringIO()
        yaml.dump(data, buf)
        cfg_path.write_text(buf.getvalue(), encoding="utf-8")
        return True

    except Exception:
        # Fallback: patch using a minimal text-based approach that edits an existing top-level `http:` block
        # (instead of blindly appending a second `http:` key, which can break YAML).
        def _patch_raw_text(raw_text: str) -> tuple[str, bool]:
            """Patch YAML text without parsing.

            Returns:
                (new_text, changed)
            """
            lines = raw_text.splitlines(keepends=True)

            # Locate a top-level `http:` key (no indentation).
            http_start: Optional[int] = None
            http_line_re = re.compile(r"^http:\s*(#.*)?\r?\n?$")
            for i, line in enumerate(lines):
                if http_line_re.match(line):
                    http_start = i
                    break

            wanted_proxies = ["127.0.0.1", "::1", "172.30.32.0/24"]

            def _is_top_level_key(line: str) -> bool:
                return bool(re.match(r"^[A-Za-z0-9_]+\s*:\s*", line)) and not line.startswith(" ")

            if http_start is None:
                # No http: block -> append a clean one.
                append_block = (
                    "\n\n"
                    "# OpenEnergy: required for secure external access through the OpenEnergy tunnel (FRP).\n"
                    "# Do not remove unless you know what you are doing.\n"
                    "http:\n"
                    "  use_x_forwarded_for: true\n"
                    "  trusted_proxies:\n"
                    "    - 127.0.0.1\n"
                    "    - ::1\n"
                    "    - 172.30.32.0/24\n"
                )
                return (raw_text + append_block, True)

            # Determine the extent of the http block (until next top-level key).
            http_end = http_start + 1
            while http_end < len(lines):
                line = lines[http_end]
                if _is_top_level_key(line) and not http_line_re.match(line):
                    break
                http_end += 1

            block = lines[http_start:http_end]

            changed = False

            # Ensure use_x_forwarded_for: true
            uxff_re = re.compile(r"^\s{2}use_x_forwarded_for:\s*(true|false)\s*(#.*)?\r?\n?$")
            uxff_idx: Optional[int] = None
            for i, line in enumerate(block):
                if uxff_re.match(line):
                    uxff_idx = i
                    if "true" not in line:
                        block[i] = re.sub(r"use_x_forwarded_for:\s*\w+", "use_x_forwarded_for: true", line)
                        changed = True
                    break

            if uxff_idx is None:
                # Insert right after `http:`
                block.insert(1, "  use_x_forwarded_for: true\n")
                changed = True

            # Ensure trusted_proxies contains wanted entries
            tp_key_re = re.compile(r"^\s{2}trusted_proxies:\s*(#.*)?\r?\n?$")
            tp_idx: Optional[int] = None
            for i, line in enumerate(block):
                if tp_key_re.match(line):
                    tp_idx = i
                    break

            if tp_idx is None:
                # Append trusted_proxies at end of http block
                if not block[-1].endswith("\n"):
                    block[-1] = block[-1] + "\n"
                block.append("  trusted_proxies:\n")
                for p in wanted_proxies:
                    block.append(f"    - {p}\n")
                changed = True
            else:
                # Collect existing list items under trusted_proxies
                j = tp_idx + 1
                existing_items: list[str] = []
                while j < len(block):
                    line = block[j]
                    # Stop at next 2-space key
                    if re.match(r"^\s{2}[A-Za-z0-9_]+\s*:\s*", line):
                        break
                    m = re.match(r"^\s{4}-\s*(.+?)\s*(#.*)?\r?\n?$", line)
                    if m:
                        existing_items.append(m.group(1).strip())
                    j += 1

                # Insert missing proxies just before the next key (at position j)
                for p in wanted_proxies:
                    if p not in existing_items:
                        block.insert(j, f"    - {p}\n")
                        j += 1
                        changed = True

            # Ensure a comment exists before http block (best-effort, only if not already there)
            if http_start > 0 and "OpenEnergy:" not in lines[http_start - 1]:
                lines.insert(
                    http_start,
                    "# OpenEnergy: required for secure external access through the OpenEnergy tunnel (FRP).\n"
                    "# Do not remove unless you know what you are doing.\n",
                )
                changed = True
                http_start += 1
                http_end += 1

            # Write back
            new_lines = lines[:http_start] + block + lines[http_end:]
            return ("".join(new_lines), changed)

        new_raw, changed = _patch_raw_text(raw)
        if not changed:
            return False

        cfg_path.write_text(new_raw, encoding="utf-8")
        return True

