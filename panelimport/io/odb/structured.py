"""Parser for ODB++ "structured text" files (matrix, stephdr, misc/info, attribute defs).

Format: ``KEY=VALUE`` lines and arrays ``NAME { KEY=VALUE ... }``.  The opening brace
may also sit on its own line after the array name.  Keys are case-insensitive and are
upper-cased; values keep their spelling but are stripped.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Block:
    name: str
    fields: dict[str, str]
    line: int


@dataclass
class StructuredText:
    fields: dict[str, str] = field(default_factory=dict)
    blocks: list[Block] = field(default_factory=list)
    # (line number, text, reason)
    problems: list[tuple[int, str, str]] = field(default_factory=list)

    def blocks_named(self, name: str) -> list[Block]:
        name = name.upper()
        return [b for b in self.blocks if b.name == name]


def parse_structured(text: str) -> StructuredText:
    out = StructuredText()
    lines = text.splitlines()
    current: Block | None = None
    pending_name: tuple[str, int] | None = None

    for idx, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        if pending_name is not None:
            name, start = pending_name
            pending_name = None
            if line == "{":
                current = Block(name, {}, start)
                continue
            out.problems.append((start, name, "expected '{' after array name"))

        if current is None:
            if line.endswith("{"):
                name = line[:-1].strip().upper()
                if not name:
                    out.problems.append((idx, raw, "array without a name"))
                current = Block(name, {}, idx)
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                out.fields[key.strip().upper()] = value.strip()
                continue
            if line == "}":
                out.problems.append((idx, raw, "unbalanced '}'"))
                continue
            if " " not in line:
                pending_name = (line.upper(), idx)
                continue
            out.problems.append((idx, raw, "unrecognized line"))
            continue

        # inside an array
        if line == "}":
            out.blocks.append(current)
            current = None
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            current.fields[key.strip().upper()] = value.strip()
            continue
        if line.endswith("{"):
            out.problems.append((idx, raw, "nested arrays are not supported"))
            continue
        out.problems.append((idx, raw, "unrecognized line inside array"))

    if pending_name is not None:
        out.problems.append((pending_name[1], pending_name[0], "array name without '{'"))
    if current is not None:
        out.problems.append((current.line, current.name, "array not closed with '}'"))
        out.blocks.append(current)
    return out
