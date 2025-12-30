from pydantic import BaseModel
class SubtitleDeleteRequest(BaseModel):
    index: int
    start: float
    end: float
