import re
from html.entities import html5

# NOTE: each is a fault in the characters themselves, so the raw HTML can hold it too.
CHARACTER_SIGNATURES = {
    "replacement character": re.compile("�"),
    "mojibake": re.compile("â€|Ã[ -¿]|Â[ -¿]"),
    "C1 control": re.compile("[\u0080-\u009f]"),
    "private use": re.compile("[-]"),
    "zero width": re.compile("[​-‍⁠﻿]"),
}
# NOTE: markup is expected in the raw HTML, so these count in derived text only.
_MARKUP_SIGNATURES = {
    "HTML entity": re.compile(r"&(?:[A-Za-z][A-Za-z0-9]*|#\d+|#x[0-9A-Fa-f]+);"),
    "HTML tag": re.compile(r"</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>"),
}
_PAIRS = {
    "unbalanced double quotes": ("“", "”"),
    "unbalanced parentheses": ("(", ")"),
}
_CONTEXT_LENGTH = 30
_PAIR_CONTEXT_LENGTH = _CONTEXT_LENGTH * 2
_NUMERIC_REFERENCE_MARKER = "#"


def get_character_fault_counts(text: str) -> dict[str, int]:
    signature_name_to_count = {name: len(pattern.findall(text)) for name, pattern in CHARACTER_SIGNATURES.items()}
    return {name: count for name, count in signature_name_to_count.items() if count}


def _get_entity_matches(text: str) -> list[re.Match]:
    # NOTE: "R&D;" is text, so a name counts only when HTML5 defines it; a numeric reference always counts.
    matches = _MARKUP_SIGNATURES["HTML entity"].finditer(text)
    return [match for match in matches if match.group(0)[1] == _NUMERIC_REFERENCE_MARKER or match.group(0)[1:] in html5]


def get_derived_text_counts(text: str) -> dict[str, int]:
    markup_name_to_count = {"HTML entity": len(_get_entity_matches(text)), "HTML tag": len(_MARKUP_SIGNATURES["HTML tag"].findall(text))}
    pair_name_to_count = {name: 1 for name in get_unbalanced_pairs(text)}
    return get_character_fault_counts(text) | {name: count for name, count in markup_name_to_count.items() if count} | pair_name_to_count


def get_unbalanced_pairs(text: str) -> list[str]:
    return [name for name, (opening, closing) in _PAIRS.items() if text.count(opening) != text.count(closing)]


def get_signature_context(text: str, signature: str) -> str:
    if signature in _PAIRS:
        return text[:_PAIR_CONTEXT_LENGTH]
    match = _get_entity_matches(text)[0] if signature == "HTML entity" else (CHARACTER_SIGNATURES | _MARKUP_SIGNATURES)[signature].search(text)
    return text[max(0, match.start() - _CONTEXT_LENGTH) : match.end() + _CONTEXT_LENGTH]
