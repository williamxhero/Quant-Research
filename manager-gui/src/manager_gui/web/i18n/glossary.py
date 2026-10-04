"""Frozen Chinese terminology shared by every catalog entry.

Catalog text references a term as `{term:<id>}`, so changing a translation here
updates the whole site. This module only holds the seed terms for now; the full
glossary is completed by the terminology ticket of the same SPEC.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

_TERM_ID = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True, slots=True)
class Term:
    """One frozen term: its English and Chinese forms and the spellings to avoid."""

    id: str
    en: str
    zh: str
    zh_short: str | None = None
    note: str | None = None
    forbidden_zh: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _TERM_ID.fullmatch(self.id):
            raise ValueError(f"term id must be lower snake_case: {self.id!r}")
        for name in ("en", "zh"):
            if not getattr(self, name).strip():
                raise ValueError(f"term {self.id!r} has an empty {name} form")
        if not isinstance(self.forbidden_zh, tuple):
            raise ValueError(f"term {self.id!r}: forbidden_zh must be a tuple")
        for spelling in self.forbidden_zh:
            if not spelling or spelling in self.zh:
                raise ValueError(f"term {self.id!r}: forbidden spelling {spelling!r} is invalid")


def _registry(terms: Iterable[Term]) -> Mapping[str, Term]:
    registry: dict[str, Term] = {}
    for term in terms:
        if term.id in registry:
            raise ValueError(f"duplicate term id: {term.id!r}")
        registry[term.id] = term
    return MappingProxyType(registry)


TERMS: Mapping[str, Term] = _registry(
    (
        Term(
            "artifact",
            "artifact",
            "制品",
            zh_short="制品",
            note="根 README 写作「不可变制品」；generated artifact 译为「生成制品」。",
            forbidden_zh=("产物",),
        ),
        Term(
            "lineage",
            "lineage",
            "谱系",
            zh_short="谱系",
            note="根 README 写作「record/artifact 和谱系」。",
            forbidden_zh=("血缘",),
        ),
        Term(
            "evidence_ledger",
            "Evidence Ledger",
            "证据账本",
            zh_short="账本",
            note="沿用 #472、#474 的「研究账本」，ledger 统一为「账本」。",
            forbidden_zh=("台账",),
        ),
        Term(
            "known",
            "Known",
            "已记录",
            zh_short="已记录",
            note="与 Missing（未记录）成对；「已确认」暗示被核实，语义偏强。",
            forbidden_zh=("已确认",),
        ),
        Term(
            "fixture",
            "fixture",
            "样例数据",
            zh_short="样例",
            note="测试夹具在界面中一律称为样例数据。",
            forbidden_zh=("夹具",),
        ),
    )
)

__all__ = ["TERMS", "Term"]
