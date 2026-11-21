from dataclasses import dataclass
from typing import Optional

from enums import PictureKind


@dataclass(frozen=True)
class ReportPictureUpdate:
    id: int
    kind: PictureKind
    content_offset: int
    follows_ordinal: Optional[int]
    typed_copy: Optional[dict[str, object]]
