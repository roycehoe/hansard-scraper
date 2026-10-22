from pydantic import BaseModel, ConfigDict


class SpeakerLinkPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    speech_id_to_speaker_id: dict[int, int]
    attendance_id_to_speaker_id: dict[int, int]
