import re

from pydantic import BaseModel, ConfigDict, RootModel, model_validator

from enums import PersonNameSpellingKind
from schemas.person_decision import PersonDecisionMember

_NOTE_LINK_RE = re.compile(r"\[[^\]]+\]\((?:https://|/reports/)[^\s)]+\)")
_MARKDOWN_LINK_MIDDLE = "]("


class PersonNameSpellingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    member: PersonDecisionMember
    spelling: str
    kind: PersonNameSpellingKind
    note: str

    @model_validator(mode="after")
    def _validate_note_links(self) -> "PersonNameSpellingEntry":
        if _NOTE_LINK_RE.search(self.note) is None:
            raise ValueError("a spelling note needs at least one source link")
        if _MARKDOWN_LINK_MIDDLE in _NOTE_LINK_RE.sub("", self.note):
            raise ValueError(
                "a spelling note links only to https addresses and /reports/ pages"
            )
        return self


class PersonNameSpellingEntries(RootModel[list[PersonNameSpellingEntry]]):
    model_config = ConfigDict(frozen=True)
