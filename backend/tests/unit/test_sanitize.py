"""HTML sanitization tests."""

from __future__ import annotations

from backend.app.security.sanitize import sanitize_html


def test_strips_script_tags() -> None:
    raw = '<p>Hello</p><script>alert("x")</script>'
    out = sanitize_html(raw)
    assert "<script>" not in out
    assert "Hello" in out


def test_allows_basic_formatting() -> None:
    raw = "<p><strong>Bold</strong> and <em>italic</em></p>"
    out = sanitize_html(raw)
    assert "<strong>" in out
    assert "<em>" in out


def test_strips_attributes() -> None:
    raw = '<p onclick="evil()">safe</p>'
    out = sanitize_html(raw)
    assert "onclick" not in out
    assert "safe" in out


def test_empty_input() -> None:
    assert sanitize_html("") == ""
    assert sanitize_html(None) == ""  # type: ignore[arg-type]


def test_lists_and_code() -> None:
    raw = "<ul><li>one</li></ul><code>x=1</code>"
    out = sanitize_html(raw)
    assert "<li>" in out
    assert "<code>" in out
