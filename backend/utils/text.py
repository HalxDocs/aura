"""Free-text sanitizers shared by the API routers.

Lives here (not in api.main) so routers that main.py mounts can import them
without a circular import; api.main re-exports the names for backwards
compatibility with existing imports/tests.
"""

import re


def sanitize_name(name: str) -> str:
    if not isinstance(name, str):
        return "Unknown"
    name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*?</\1>', '', name, flags=re.IGNORECASE | re.DOTALL)
    name = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*', '', name, flags=re.IGNORECASE | re.DOTALL)
    name = re.sub(r'<[^>]+>', '', name)
    name = name[:100]
    name = re.sub(r'\s+', ' ', name).strip()
    return name or "Unknown"


def sanitize_text(text: str, max_length: int) -> str:
    """Strip HTML tags and cap length for free-text inputs (job descriptions, etc.)."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:max_length]


def sanitize_rich_text(text: str, max_length: int | None, *, preserve_newlines: bool = False) -> str:
    """Like sanitize_text, but also drops the *content* of active tags.

    Profile fields are stored verbatim and re-rendered in dashboards, so a
    pasted ``<script>…</script>`` must not leave its payload behind as text
    the way plain tag-stripping would.

    With ``preserve_newlines`` the line structure survives — runs of
    horizontal whitespace still collapse to single spaces, but paragraph
    breaks in prose fields (summaries, role descriptions) are not flattened
    into one long line.

    ``max_length=None`` skips the cap — for callers that sanitize first and
    apply their own cap afterwards.
    """
    if not isinstance(text, str):
        return ""
    text = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*?</\1>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<(script|style|iframe|object|embed)[^>]*>.*', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    if preserve_newlines:
        # \s would eat the newlines; [^\S\n] is "whitespace except \n".
        text = re.sub(r'[^\S\n]+', ' ', text).strip()
    else:
        text = re.sub(r'\s+', ' ', text).strip()
    return text if max_length is None else text[:max_length]
