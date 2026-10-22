import re
from dataclasses import dataclass

_NON_ASCII_RUN_PATTERN = re.compile(r"[^\x00-\x7f]+")


@dataclass(frozen=True)
class TextChange:
    id: int
    before: str
    after: str


def _fix_mojibake_run(match: re.Match) -> str:
    try:
        return match.group(0).encode("cp1252").decode("utf-8")
    except UnicodeDecodeError:
        return match.group(0)
    except UnicodeEncodeError:
        return match.group(0)


def fix_mojibake(text: str) -> str:
    # NOTE: a whole-text decode fails on one correct character, so each run is repaired alone.
    return _NON_ASCII_RUN_PATTERN.sub(_fix_mojibake_run, text)


def strip_nul(value_tree: object) -> object:
    if isinstance(value_tree, str):
        return value_tree.replace("\x00", "")
    if isinstance(value_tree, dict):
        return {key: strip_nul(value) for key, value in value_tree.items()}
    if isinstance(value_tree, list):
        return [strip_nul(value) for value in value_tree]
    return value_tree
