from __future__ import annotations

from app.services.script_utils import detect_scripts, split_text_by_script


def test_split_text_by_script_preserves_order() -> None:
    segments = split_text_by_script("你好, world! 再见.")
    assert [(segment.script, segment.text) for segment in segments] == [
        ("cjk", "你好,"),
        ("latin", "world!"),
        ("cjk", "再见."),
    ]


def test_detect_scripts_finds_bilingual_text() -> None:
    assert detect_scripts("你好 world") == ["cjk", "latin"]
