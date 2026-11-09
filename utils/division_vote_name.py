from dataclasses import dataclass

from enums import DivisionVoteChoice


@dataclass(frozen=True)
class ParsedVoteName:
    ordinal: int
    printed_name: str
    vote_choice: DivisionVoteChoice


_TRAILING_TITLES = frozenset({"madam", "miss", "mrs", "mr", "dr"})


def _strip_final_period(name: str) -> str:
    last_word = name.split()[-1]
    if not last_word.endswith("."):
        return name
    last_word_without_period = last_word[:-1]
    if "." in last_word_without_period or len(last_word_without_period) == 1:
        return name
    return name[:-1]


def get_name_to_resolve(printed_name: str) -> str:
    name = _strip_final_period(printed_name.strip())
    words = name.split()
    if len(words) > 1 and words[-1].rstrip(".").lower() in _TRAILING_TITLES:
        name = _strip_final_period(name[: -len(words[-1])].strip())
    return name
