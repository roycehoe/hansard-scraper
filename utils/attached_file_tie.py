from dataclasses import dataclass


@dataclass(frozen=True)
class AttachedFilePointerTie:
    attached_file_pointer_id: int
    attached_file_id: int
