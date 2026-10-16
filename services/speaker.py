from database.speaker import Speaker
from schemas.speaker import SpeakerResult


def build_speaker(speaker_result: SpeakerResult, name_parliament_to_is_legislative_assembly: dict[tuple[str, int], bool]) -> Speaker:
    is_legislative_assembly = name_parliament_to_is_legislative_assembly.get(
        (speaker_result.name, speaker_result.parliament_number), speaker_result.is_legislative_assembly
    )
    return Speaker(**speaker_result.model_dump(exclude={"is_legislative_assembly"}), is_legislative_assembly=is_legislative_assembly)
