def fix_mojibake(text: str) -> str:
    try:
        return text.encode("cp1252").decode("utf-8")
    except UnicodeDecodeError:
        return text
    except UnicodeEncodeError:
        return text
