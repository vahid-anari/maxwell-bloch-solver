"""Renames for parameter keys used in older parameter files."""

from __future__ import annotations

from typing import Any, Dict
import copy

LEGACY_KEY_RENAMES = {
    "solve.dynamics.t1": "solve.t1",
    "solve.dynamics.t2": "solve.t2",
    "solve.pump.cosh1": "solve.pump.pulse1",
    "solve.pump.cosh2": "solve.pump.pulse2",
    "solve.pump.cosh3": "solve.pump.pulse3",
}
"""Mapping from parameter keys used in older files to their current names."""


def migrate_legacy_keys(params: Dict[str, Any]) -> Dict[str, Any]:
    """Rename keys from older parameter files to their current names.

    If a mapping contains both the old and the new key, the new key wins.

    Args:
        params: Parameter mapping keyed by widget path.

    Returns:
        New mapping with legacy keys renamed.
    """

    migrated = {k: v for k, v in params.items() if k not in LEGACY_KEY_RENAMES}
    for old, new in LEGACY_KEY_RENAMES.items():
        if old in params and new not in migrated:
            migrated[new] = params[old]
    return migrated


def merge_onto_defaults(base: Dict[str, Any], saved: Dict[str, Any]) -> Dict[str, Any]:
    """Overlay saved values onto a defaults mapping, recursively.

    Only keys present in ``base`` are kept, so keys removed from the app are
    dropped and keys added since the save keep their default value. Nested
    dicts are merged; any other value (including lists) is replaced whole.

    Args:
        base: Default mapping defining the valid keys.
        saved: Previously saved mapping to overlay.

    Returns:
        New merged mapping; neither input is modified.
    """

    merged = copy.deepcopy(base)
    for key, base_val in base.items():
        if key not in saved:
            continue
        saved_val = saved[key]
        if isinstance(base_val, dict) and isinstance(saved_val, dict):
            merged[key] = merge_onto_defaults(base_val, saved_val)
        elif isinstance(base_val, dict) or isinstance(saved_val, dict):
            continue  # shape changed between versions: keep the default
        else:
            merged[key] = copy.deepcopy(saved_val)
    return merged
