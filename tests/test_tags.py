from __future__ import annotations

import pytest

from oslo.models import SystemTag
from oslo.tags import TagError, matches, parse_tags, replace_tags


def test_parse_tags():
    assert parse_tags(["Dev, internetfacing", " sla = 1 ", ""]) == {
        "dev": "",
        "internetfacing": "",
        "sla": "1",
    }
    assert parse_tags(["zone=EU-West.2"]) == {"zone": "EU-West.2"}
    assert parse_tags([]) == {}


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("bad tag", "tag_invalid"),
        ("-dev", "tag_invalid"),
        ("sla=", "tag_invalid"),
        ("sla=a b", "tag_invalid"),
        ("x" * 33, "tag_invalid"),
        ("sla=1, sla=2", "tag_duplicate"),
        (",".join(f"t{i}" for i in range(51)), "tag_too_many"),
    ],
)
def test_invalid_tags(text, code):
    with pytest.raises(TagError) as info:
        parse_tags([text])
    assert info.value.code == code


def test_matches_key_or_pair():
    tags = [SystemTag(key="dev", value=""), SystemTag(key="sla", value="1")]
    assert matches(tags, ["dev"])
    assert matches(tags, ["sla"])  # key alone matches any value
    assert matches(tags, ["sla=1"])
    assert not matches(tags, ["sla=2"])
    assert matches(tags, ["prod", "sla=1"])  # one matching tag is enough
    assert not matches(tags, ["prod", "bad tag"])
    assert not matches([], ["dev"])


def test_replace_tags_updates_in_place():
    tags = [SystemTag(key="dev", value=""), SystemTag(key="sla", value="1")]
    sla = tags[1]
    replace_tags(tags, SystemTag, {"sla": "2", "internetfacing": ""})
    assert [(t.key, t.value) for t in tags] == [("sla", "2"), ("internetfacing", "")]
    assert tags[0] is sla
