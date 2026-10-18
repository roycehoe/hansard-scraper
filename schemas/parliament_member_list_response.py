from pydantic import BaseModel

from enums import LegislativeAssemblyFlag


class ParliamentMemberSession(BaseModel):
    parliament_sessions_id: str


class ParliamentMember(BaseModel):
    full_name: str
    # NOTE: the misspelling is the source's field name
    party_affliation: str
    legislative_assembly: LegislativeAssemblyFlag
    parliament_session: list[ParliamentMemberSession]


class ParliamentMembersMeta(BaseModel):
    filter_count: int


class ParliamentMembers(BaseModel):
    meta: ParliamentMembersMeta
    data: list[ParliamentMember]


class ParliamentOption(BaseModel):
    title: str
    parliament_sessions: list[str]


class ParliamentMemberListResponse(BaseModel):
    mps: ParliamentMembers
    options: list[ParliamentOption]
