"""Human-readable provider / quota error helpers."""

from __future__ import annotations

DAILY_EMBED_QUOTA_MESSAGE = "Daily free-tier embedding quota reached, resets at midnight Pacific"


def is_daily_embed_quota_error(exc: BaseException | str) -> bool:
    """True when Google reports free-tier *daily* EmbedContent exhaustion."""
    text = str(exc)
    upper = text.upper()
    if "RESOURCE_EXHAUSTED" not in upper and "429" not in upper:
        return False
    # quotaId contains PerDay; metric name contains embed_content
    has_per_day = "PERDAY" in upper.replace("_", "") or "PER_DAY" in upper
    has_embed = (
        "EMBEDCONTENT" in upper.replace("_", "")
        or "EMBED_CONTENT" in upper
        or "gemini-embedding" in text.lower()
    )
    return has_per_day and has_embed


def humanize_provider_error(exc: BaseException | str) -> str:
    """Map known provider quota failures to short UI-safe messages."""
    if is_daily_embed_quota_error(exc):
        return DAILY_EMBED_QUOTA_MESSAGE
    return str(exc)


class DailyEmbedQuotaError(RuntimeError):
    """Raised when EmbedContent daily free-tier quota is exhausted."""

    def __init__(self, message: str = DAILY_EMBED_QUOTA_MESSAGE) -> None:
        super().__init__(message)
