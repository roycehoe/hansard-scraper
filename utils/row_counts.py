from collections import Counter


def format_row_counts(key_to_row_count: Counter) -> str:
    return (
        ", ".join(
            f"{key} {row_count:,}"
            for key, row_count in sorted(key_to_row_count.items())
        )
        or "none"
    )
