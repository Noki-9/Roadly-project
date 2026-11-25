import re

from pydantic import BaseModel, Field, field_validator

LEVELS = {"новичок", "базовый", "средний", "продвинутый"}
PACES = {"спокойный", "сбалансированный", "интенсивный"}

# ---------------------------------------------------------------------------
# Схемы
# ---------------------------------------------------------------------------
class RoadmapRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=800)
    level: str = Field(default="новичок", max_length=32)
    pace: str = Field(default="сбалансированный", max_length=32)
    horizon: str = Field(default="3 месяца", max_length=32)

    @field_validator("prompt")
    @classmethod
    def clean_prompt(cls, value: str) -> str:
        value = re.sub(r"\s+", " ", value).strip()
        if len(value) < 10:
            raise ValueError("Слишком короткий запрос")
        return value

    @field_validator("level")
    @classmethod
    def clean_level(cls, value: str) -> str:
        return value if value in LEVELS else "новичок"

    @field_validator("pace")
    @classmethod
    def clean_pace(cls, value: str) -> str:
        return value if value in PACES else "сбалансированный"

    @field_validator("horizon")
    @classmethod
    def clean_horizon(cls, value: str) -> str:
        allowed = {"1 месяц", "3 месяца", "6 месяцев", "1 год"}
        return value if value in allowed else "3 месяца"


class Resource(BaseModel):
    title: str
    url: str = ""


class Phase(BaseModel):
    title: str
    duration: str = ""
    description: str = ""
    tasks: list[str] = Field(default_factory=list)
    outcome: str = ""


class Roadmap(BaseModel):
    title: str
    summary: str = ""
    duration: str = ""
    level: str = ""
    phases: list[Phase]
    skills: list[str] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)
    demo: bool = False


class ProgressUpdate(BaseModel):
    done_tasks: list[str] = Field(default_factory=list, max_length=500)

