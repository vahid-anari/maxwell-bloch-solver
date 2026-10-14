"""Renames for parameter keys used in older parameter files."""

from __future__ import annotations

from typing import Any, Dict
import copy

LEGACY_KEY_RENAMES: Dict[str, str] = {
    "solve.dynamics.t1": "solve.t1",
    "solve.dynamics.t2": "solve.t2",
    "solve.pump.cosh1": "solve.pump.pulse1",
    "solve.pump.cosh2": "solve.pump.pulse2",
    "solve.pump.cosh3": "solve.pump.pulse3",
}
"""Mapping from parameter keys used in older files to their current names."""

ADDED_PARAM_DEFAULTS: Dict[str, Any] = {
    "results.scale.normalize": True,
}
"""Parameter keys added in newer versions, with values reproducing old behaviour."""

ADDED_CONFIG_DEFAULTS: Dict[str, Any] = {
    "results.scale.normalize": {},
}
"""Config keys added in newer versions, with their default configuration."""


def rename_legacy_keys(params: Dict[str, Any]) -> Dict[str, Any]:
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


def add_missing_keys(mapping: Dict[str, Any], defaults: Dict[str, Any]) -> Dict[str, Any]:
    """Add keys introduced in newer versions that older files do not contain.

    Existing values are never overwritten.

    Args:
        mapping: Parameter or config mapping keyed by widget path.
        defaults: Keys to add and their default values.

    Returns:
        New mapping with missing keys filled in.
    """

    migrated = dict(mapping)
    for key, default in defaults.items():
        if key not in migrated:
            migrated[key] = copy.deepcopy(default)
    return migrated


def migrate_legacy_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """Bring a parameter mapping from an older file up to the current format.

    Args:
        params: Parameter mapping keyed by widget path.

    Returns:
        New, fully migrated mapping.
    """

    return add_missing_keys(rename_legacy_keys(params), ADDED_PARAM_DEFAULTS)


def migrate_legacy_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Bring a config mapping from an older file up to the current format.

    Args:
        config: Config mapping keyed by widget path.

    Returns:
        New, fully migrated mapping.
    """

    return add_missing_keys(rename_legacy_keys(config), ADDED_CONFIG_DEFAULTS)


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
