from __future__ import annotations

from app.services.script_utils import detect_scripts, split_text_by_script, split_text_into_paragraphs


def test_split_text_by_script_preserves_order() -> None:
    segments = split_text_by_script("\u4f60\u597d, world! \u518d\u89c1.")
    assert [(segment.script, segment.text) for segment in segments] == [
        ("cjk", "\u4f60\u597d,"),
        ("latin", "world!"),
        ("cjk", "\u518d\u89c1."),
    ]


def test_detect_scripts_finds_bilingual_text() -> None:
    assert detect_scripts("\u4f60\u597d world") == ["cjk", "latin"]


def test_split_text_into_paragraphs_normalizes_wrapped_ocr_lines() -> None:
    chunks = split_text_into_paragraphs("Distil-\nler is here.\nNext line continues.")
    assert chunks == ["Distiller is here. Next line continues."]


def test_split_text_into_paragraphs_chunks_long_sentence_groups() -> None:
    chunks = split_text_into_paragraphs(
        "One short sentence. Two short sentence. Three short sentence. Four short sentence.",
        max_chars=40,
    )
    assert len(chunks) >= 2
    assert all(len(chunk) <= 40 for chunk in chunks)
