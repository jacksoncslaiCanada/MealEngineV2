from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class RawRecipeSchema(BaseModel):
    source: Literal["reddit", "youtube"]
    source_id: str
    raw_content: str
    url: str
    fetched_at: datetime

    model_config = {"from_attributes": True}
