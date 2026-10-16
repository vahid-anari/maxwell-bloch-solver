"""Tests for the update check: version parsing and picking the release notes."""

import pytest

from mbstudio.app.update_checker import MAX_NOTES, newer_release_notes, parse_version


@pytest.mark.parametrize(
    "text, expected",
    [
        ("10.0.4", (10, 0, 4)),
        ("v10.0.4", (10, 0, 4)),
        ("V8.6", (8, 6)),
        (" 9.1.1 ", (9, 1, 1)),
        ("0+unknown", (0,)),
        ("", ()),
    ],
)
def test_parse_version(text, expected):
    assert parse_version(text) == expected


def test_versions_compare_as_numbers():
    assert parse_version("10.0.10") > parse_version("10.0.9")
    assert parse_version("10.0.0") > parse_version("9.2.0")


RELEASES = [
    {"tag_name": "v10.0.6", "body": "- six"},
    {"tag_name": "v10.0.5", "body": "- five"},
    {"tag_name": "v10.0.4", "body": "- four"},
    {"tag_name": "v10.0.3", "body": "- three"},
    {"tag_name": "v10.0.2", "body": "- two"},
]


def test_picks_versions_after_current_up_to_latest():
    notes = newer_release_notes(RELEASES, current="10.0.2", latest="10.0.5")
    assert notes == [("10.0.5", "- five"), ("10.0.4", "- four"), ("10.0.3", "- three")]


def test_nothing_newer():
    assert newer_release_notes(RELEASES, current="10.0.6", latest="10.0.6") == []


def test_newest_first_whatever_the_order():
    notes = newer_release_notes(list(reversed(RELEASES)), current="10.0.3", latest="10.0.6")
    assert [v for v, _ in notes] == ["10.0.6", "10.0.5", "10.0.4"]


def test_skips_drafts_prereleases_and_empty_notes():
    releases = [
        {"tag_name": "v10.0.5", "body": "- five", "draft": True},
        {"tag_name": "v10.0.4", "body": "- four", "prerelease": True},
        {"tag_name": "v10.0.3", "body": "   "},
        {"tag_name": "v10.0.2", "body": None},
        {"tag_name": "v10.0.1", "body": "- one"},
    ]
    assert newer_release_notes(releases, current="10.0.0", latest="10.0.5") == [("10.0.1", "- one")]


def test_ignores_junk_entries():
    releases = ["junk", None, {"body": "no tag"}, {"tag_name": "nightly", "body": "x"},
                {"tag_name": "v10.0.1", "body": "- one"}]
    assert newer_release_notes(releases, current="10.0.0", latest="10.0.1") == [("10.0.1", "- one")]


def test_strips_notes():
    releases = [{"tag_name": "v10.0.1", "body": "\n- one\n\n"}]
    assert newer_release_notes(releases, current="10.0.0", latest="10.0.1") == [("10.0.1", "- one")]


def test_limit():
    releases = [{"tag_name": f"v10.0.{i}", "body": f"- {i}"} for i in range(1, 30)]
    notes = newer_release_notes(releases, current="10.0.0", latest="10.0.29")
    assert len(notes) == MAX_NOTES
    assert notes[0][0] == "10.0.29"
