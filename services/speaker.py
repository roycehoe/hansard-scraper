from database.speaker import Speaker
from schemas.speaker import SpeakerResult


def build_speaker(speaker_result: SpeakerResult) -> Speaker:
    return Speaker(**speaker_result.model_dump())
