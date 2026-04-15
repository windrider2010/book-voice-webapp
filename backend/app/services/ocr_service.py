from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image

from app.services.script_utils import detect_scripts


@dataclass(slots=True)
class RecognizedBlock:
    text: str
    confidence: float | None
    box: list[list[float]]


@dataclass(slots=True)
class RecognizedPage:
    text: str
    blocks: list[RecognizedBlock]
    detected_scripts: list[str]


class OcrService(Protocol):
    def recognize(self, image: Image.Image, lang_hint: str | None = None) -> RecognizedPage:
        """Recognize text in a normalized image."""


class PaddleOcrService:
    def __init__(self, *, use_gpu: bool = False) -> None:
        self._use_gpu = use_gpu
        self._lock = threading.Lock()
        self._engines: dict[str, Any] = {}

    def recognize(self, image: Image.Image, lang_hint: str | None = None) -> RecognizedPage:
        try:
            import numpy as np
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("numpy is required for OCR preprocessing.") from exc

        engine = self._get_engine(_resolve_paddle_language(lang_hint))
        image_array = np.array(image)
        blocks = self._extract_blocks(engine, image_array)
        text = "\n".join(block.text for block in blocks if block.text.strip())
        return RecognizedPage(text=text, blocks=blocks, detected_scripts=detect_scripts(text))

    def _get_engine(self, language: str) -> Any:
        with self._lock:
            cached = self._engines.get(language)
            if cached is not None:
                return cached
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "PaddleOCR is unavailable. Run `uv sync --project backend` to install OCR dependencies."
                ) from exc

            engine = PaddleOCR(
                lang=language,
                device="gpu:0" if self._use_gpu else "cpu",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
            )
            self._engines[language] = engine
            return engine

    def _extract_blocks(self, engine: Any, image_array: Any) -> list[RecognizedBlock]:
        if hasattr(engine, "ocr"):
            result = engine.ocr(image_array, cls=True)
            return _parse_legacy_result(result)
        if hasattr(engine, "predict"):
            result = engine.predict(image_array)
            return _parse_predict_result(result)
        raise RuntimeError("Unsupported PaddleOCR engine API.")


def _resolve_paddle_language(lang_hint: str | None) -> str:
    hint = (lang_hint or "bilingual").strip().lower()
    if hint == "en":
        return "en"
    return "ch"


def _parse_legacy_result(result: Any) -> list[RecognizedBlock]:
    rows = result[0] if isinstance(result, list) and result and isinstance(result[0], list) else result
    blocks: list[RecognizedBlock] = []
    if not isinstance(rows, list):
        return blocks
    for line in rows:
        if not isinstance(line, (list, tuple)) or len(line) < 2:
            continue
        box_raw = line[0]
        text_raw = line[1]
        text = ""
        confidence: float | None = None
        if isinstance(text_raw, (list, tuple)) and text_raw:
            text = str(text_raw[0]).strip()
            if len(text_raw) > 1:
                try:
                    confidence = float(text_raw[1])
                except (TypeError, ValueError):
                    confidence = None
        box = _coerce_box(box_raw)
        if text:
            blocks.append(RecognizedBlock(text=text, confidence=confidence, box=box))
    return blocks


def _parse_predict_result(result: Any) -> list[RecognizedBlock]:
    blocks: list[RecognizedBlock] = []
    for item in result or []:
        payload = getattr(item, "res", item)
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        if hasattr(item, "json") and not isinstance(payload, dict):
            json_value = getattr(item, "json")
            if isinstance(json_value, str):
                try:
                    payload = json.loads(json_value)
                except json.JSONDecodeError:
                    payload = payload
        if not isinstance(payload, dict):
            continue
        texts = payload.get("rec_texts") or []
        scores = payload.get("rec_scores") or []
        polys = payload.get("rec_polys") or payload.get("dt_polys") or []
        for index, text in enumerate(texts):
            confidence = None
            if index < len(scores):
                try:
                    confidence = float(scores[index])
                except (TypeError, ValueError):
                    confidence = None
            box = _coerce_box(polys[index] if index < len(polys) else [])
            chunk = str(text).strip()
            if chunk:
                blocks.append(RecognizedBlock(text=chunk, confidence=confidence, box=box))
    return blocks


def _coerce_box(raw_box: Any) -> list[list[float]]:
    points: list[list[float]] = []
    if not isinstance(raw_box, (list, tuple)):
        return points
    for point in raw_box:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            points.append([float(point[0]), float(point[1])])
        except (TypeError, ValueError):
            continue
    return points
