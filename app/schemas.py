"""Request and response formats for the scoring API."""
from typing import Literal

from pydantic import BaseModel, Field


class Lead(BaseModel):
    """One lead, using the same cleaned columns the model was trained on.

    Only a few fields are required; the rest default to "Unknown" / 0,
    the same values preprocess.py uses for missing data.
    """

    lead_origin: str = Field(examples=["Landing Page Submission"])
    lead_source: str = Field("Unknown", examples=["Google"])
    do_not_email: int = Field(0, ge=0, le=1)
    do_not_call: int = Field(0, ge=0, le=1)
    totalvisits: float = Field(0, ge=0, examples=[3])
    total_time_spent_on_website: float = Field(0, ge=0, examples=[600])
    page_views_per_visit: float = Field(0, ge=0, examples=[2.5])
    last_activity: str = Field("Unknown", examples=["Email Opened"])
    country: str = "Unknown"
    specialization: str = "Unknown"
    what_is_your_current_occupation: str = Field("Unknown", examples=["Working Professional"])
    what_matters_most_to_you_in_choosing_a_course: str = "Unknown"
    search: int = Field(0, ge=0, le=1)
    newspaper_article: int = Field(0, ge=0, le=1)
    x_education_forums: int = Field(0, ge=0, le=1)
    newspaper: int = Field(0, ge=0, le=1)
    digital_advertisement: int = Field(0, ge=0, le=1)
    through_recommendations: int = Field(0, ge=0, le=1)
    city: str = "Unknown"
    a_free_copy_of_mastering_the_interview: int = Field(0, ge=0, le=1)


class Reason(BaseModel):
    feature: str
    value: str
    effect: Literal["increases", "decreases"]
    impact: float


class FollowUp(BaseModel):
    next_action: str
    email_opener: str | None = None
    source: Literal["llm", "template"]


class Prediction(BaseModel):
    prediction_id: str
    probability: float
    band: Literal["Hot", "Warm", "Cold"]
    reasons: list[Reason]
    follow_up: FollowUp
    model_version: str
    variant: Literal["champion", "canary"]


class Feedback(BaseModel):
    prediction_id: str
    converted: bool
