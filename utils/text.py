import re

_NON_ASCII_RUN_PATTERN = re.compile(r"[^\x00-\x7f]+")


def _fix_mojibake_run(match: re.Match) -> str:
    try:
        return match.group(0).encode("cp1252").decode("utf-8")
    except UnicodeDecodeError:
        return match.group(0)
    except UnicodeEncodeError:
        return match.group(0)


def fix_mojibake(text: str) -> str:
    # NOTE: each run of non-ASCII characters is repaired on its own, so a correct "’" elsewhere in the text does not block the fix.
    return _NON_ASCII_RUN_PATTERN.sub(_fix_mojibake_run, text)


def strip_nul(value_tree: object) -> object:
    if isinstance(value_tree, str):
        return value_tree.replace("\x00", "")
    if isinstance(value_tree, dict):
        return {key: strip_nul(value) for key, value in value_tree.items()}
    if isinstance(value_tree, list):
        return [strip_nul(value) for value in value_tree]
    return value_tree
