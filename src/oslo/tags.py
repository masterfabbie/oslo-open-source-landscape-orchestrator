"""Tags of hosts and systems: a key with an optional value, e.g. "dev" or "sla=1".

Keys are lowercase letters, digits, "-" and "_"; values may also contain "." and capital
letters. Each key occurs at most once per host or system.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from .models import HostTag, SystemTag

KEY_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
VALUE_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,64}")
MAX_TAGS = 50


class TagError(ValueError):
    """A tag text is not valid."""

    def __init__(self, code: str, message: str, tag: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.tag = tag


def parse_tag(text: str) -> tuple[str, str]:
    """"Sla = 1" -> ("sla", "1"); "Dev" -> ("dev", "")."""
    key, _, value = text.partition("=")
    key, value = key.strip().lower(), value.strip()
    if not KEY_PATTERN.fullmatch(key):
        raise TagError("tag_invalid", f"Invalid tag: {text.strip()!r}", text.strip())
    if "=" in text and not VALUE_PATTERN.fullmatch(value):
        raise TagError("tag_invalid", f"Invalid tag value: {text.strip()!r}", text.strip())
    return key, value


def parse_tags(texts: Iterable[str]) -> dict[str, str]:
    """Tags from texts; each text may hold several tags separated by commas.

    Raises :class:`TagError` for invalid tags, a key given twice or too many tags.
    """
    tags: dict[str, str] = {}
    for text in texts:
        for part in text.split(","):
            if not part.strip():
                continue
            key, value = parse_tag(part)
            if key in tags:
                raise TagError("tag_duplicate", f"Tag key given twice: {key}", key)
            tags[key] = value
    if len(tags) > MAX_TAGS:
        raise TagError("tag_too_many", f"At most {MAX_TAGS} tags")
    return tags


def tag_text(key: str, value: str) -> str:
    return f"{key}={value}" if value else key


def tag_texts(tags: Sequence[HostTag | SystemTag]) -> list[str]:
    return [tag.text for tag in tags]


def replace_tags(owner_tags: list, tag_class: type, tags: dict[str, str]) -> None:
    """Replace the tags of a host or system. The caller commits.

    Existing keys are updated in place: deleting and inserting the same key in one flush
    would collide on the primary key.
    """
    existing = {tag.key: tag for tag in owner_tags}
    for key in existing.keys() - tags.keys():
        owner_tags.remove(existing[key])
    for key, value in sorted(tags.items()):
        if key in existing:
            existing[key].value = value
        else:
            owner_tags.append(tag_class(key=key, value=value))


def matches(tags: Sequence[HostTag | SystemTag], wanted: Iterable[str]) -> bool:
    """Whether one of ``wanted`` matches: "key" matches the key with any value,
    "key=value" only that value."""
    have = {(tag.key, tag.value) for tag in tags}
    keys = {key for key, _ in have}
    for text in wanted:
        try:
            key, value = parse_tag(text)
        except TagError:
            continue
        if ("=" in text and (key, value) in have) or ("=" not in text and key in keys):
            return True
    return False
