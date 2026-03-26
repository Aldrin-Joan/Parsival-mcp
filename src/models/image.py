from __future__ import annotations
from pydantic import BaseModel, computed_field


class ImageRef(BaseModel):
    index: int
    page: int | None = None
    width_px: int | None = None
    height_px: int | None = None
    format: str
    size_bytes: int
    base64_data: str
    description_hint: str
    confidence: float
    alt_text: str | None = None

    @computed_field
    @property
    def data_uri(self) -> str:
        return f"data:image/{self.format};base64,{self.base64_data}"
