"""HTML sanitization for user-facing text fields."""

from __future__ import annotations

import bleach

_ALLOWED_TAGS = ["p", "br", "strong", "em", "ul", "ol", "li", "code"]
_ALLOWED_ATTRIBUTES: dict[str, list[str]] = {}


def sanitize_html(text: str) -> str:
    """Strip dangerous HTML; allow only basic formatting tags.

    Allowed tags: ``p``, ``br``, ``strong``, ``em``, ``ul``, ``ol``, ``li``, ``code``.
    All attributes are stripped.
    """
    if not text:
        return ""
    return bleach.clean(
        text,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        strip=True,
    )
