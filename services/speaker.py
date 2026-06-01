from database.speaker import Speaker
from schemas.speaker import SpeakerResult


def build_speaker(result: SpeakerResult) -> Speaker:
    return Speaker(**result.model_dump())
