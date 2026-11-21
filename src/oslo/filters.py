"""Values of the landscape filters.

Filtering itself happens in the browser (frontend/src/landscape/filter.ts) on the data of
/api/landscape: within one filter one match is enough, all filters must match.
"""

from __future__ import annotations

from .models import STATUS_UNKNOWN

STATUS_VALUES = ("GREEN", "YELLOW", "RED", "GRAY", STATUS_UNKNOWN)
REACH_VALUES = ("GREEN", "RED", STATUS_UNKNOWN)
TYPE_VALUES = ("hana", "scs", "ers", "abap", "java", "dual", "agent")

# Names of the filter values in the address of the landscape page; the language switch
# keeps them.
PARAMS = frozenset(
    {"q", "hq", "status", "pool", "type", "tag", "hosttag", "reach", "agent", "htag"}
)
