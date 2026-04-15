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
