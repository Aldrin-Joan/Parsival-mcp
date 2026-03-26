from src.models.image import ImageRef


def test_image_data_uri():
    img = ImageRef(
        index=0,
        page=1,
        width_px=100,
        height_px=100,
        format="png",
        size_bytes=10,
        base64_data="aGVsbG8=",
        description_hint="Demo",
        confidence=0.92,
    )
    assert img.data_uri.startswith("data:image/png;base64,")
