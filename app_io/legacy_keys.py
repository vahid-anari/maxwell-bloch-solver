"""Renames for parameter keys used in older parameter files."""

from __future__ import annotations

from typing import Any, Dict

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