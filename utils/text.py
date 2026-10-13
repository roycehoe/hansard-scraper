def fix_mojibake(text: str) -> str:
    try:
        return text.encode("cp1252").decode("utf-8")
    except UnicodeDecodeError:
        return text
    except UnicodeEncodeError:
        return text


def strip_nul(value_tree: object) -> object:
    if isinstance(value_tree, str):
        return value_tree.replace("\x00", "")
    if isinstance(value_tree, dict):
        return {key: strip_nul(value) for key, value in value_tree.items()}
    if isinstance(value_tree, list):
        return [strip_nul(value) for value in value_tree]
    return value_tree
