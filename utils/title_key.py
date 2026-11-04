import re

_NON_KEY_PATTERN = re.compile(r"[\W_]+")


def get_title_key(title: str) -> str:
    return _NON_KEY_PATTERN.sub("", title.lower())
