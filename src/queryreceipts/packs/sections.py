"""Sectioned-capture support shared by all engine packs.

Captures may bracket regions with ====BEGIN_SECTION:name==== /
====END_SECTION:name==== markers (PRINT in T-SQL, \\echo in psql)."""
from __future__ import annotations

import re

SECTION_BEGIN = "====BEGIN_SECTION:{name}===="
SECTION_END = "====END_SECTION:{name}===="


class SectionNotFound(Exception):
    pass


def extract_section(text: str, name: str) -> str:
    if "====BEGIN_SECTION:" not in text:
        return text  # unmarked capture: the whole file is the section
    begin = SECTION_BEGIN.format(name=name)
    if begin not in text:
        found = sorted(set(re.findall(r"====BEGIN_SECTION:(\w+)====", text)))
        raise SectionNotFound(
            f"section {name!r} not in capture; sections present: {found}")
    start = text.index(begin) + len(begin)
    end = SECTION_END.format(name=name)
    stop = text.index(end, start) if end in text else len(text)
    return text[start:stop]
