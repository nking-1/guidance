import collections.abc

from typing import Union

import guidance
from .._grammar import capture

from ._char_range import char_range
from ._one_or_more import one_or_more
from ._optional import optional


@guidance(stateless=True)
def _gen_json_int(lm):
    return lm + optional("-") + one_or_more(char_range("0", "9"))


@guidance(stateless=True)
def gen_json(
    lm,
    name: Union[str, None] = None,
    *,
    json_schema: collections.abc.Mapping[str, any],
    json_schema_refs: collections.abc.MutableMapping[str, any] = dict()
):
    _DEFS_KEY = "$defs"
    if _DEFS_KEY in json_schema:
        json_schema_refs.update(json_schema[_DEFS_KEY])

    if json_schema["type"] == "integer":
        return lm + _gen_json_int()
