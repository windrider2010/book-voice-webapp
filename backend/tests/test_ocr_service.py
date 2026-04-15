from __future__ import annotations

import sys
from types import SimpleNamespace

from app.services.ocr_service import PaddleOcrService


def test_paddle_ocr_service_uses_device_kwarg_for_paddleocr_v3(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class FakePaddleOCR:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=FakePaddleOCR))

    cpu_service = PaddleOcrService(use_gpu=False)
    cpu_service._get_engine("ch")
    assert captured["device"] == "cpu"
    assert captured["lang"] == "ch"
    assert captured["use_doc_orientation_classify"] is False
    assert captured["use_doc_unwarping"] is False
    assert captured["use_textline_orientation"] is False

    gpu_service = PaddleOcrService(use_gpu=True)
    gpu_service._get_engine("en")
    assert captured["device"] == "gpu:0"
    assert captured["lang"] == "en"


def test_paddle_ocr_service_prefers_predict_over_legacy_ocr() -> None:
    class FakeEngine:
        def ocr(self, *_args, **_kwargs):
            raise AssertionError("legacy ocr path should not be used when predict exists")

        def predict(self, _image):
            return [
                {
                    "rec_texts": ["hello"],
                    "rec_scores": [0.99],
                    "rec_polys": [[[0, 0], [1, 0], [1, 1], [0, 1]]],
                }
            ]

    service = PaddleOcrService()
    blocks = service._extract_blocks(FakeEngine(), image_array=None)
    assert len(blocks) == 1
    assert blocks[0].text == "hello"
