from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    script: str
    text: str


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0x3040 <= code <= 0x309F
        or 0x30A0 <= code <= 0x30FF
        or 0xAC00 <= code <= 0xD7AF
    )


def _char_script(char: str) -> str:
    if _is_cjk(char):
        return "cjk"
    if char.isascii() and (char.isalpha() or char.isdigit()):
        return "latin"
    return "neutral"


def detect_scripts(text: str) -> list[str]:
    seen: list[str] = []
    for char in text:
        script = _char_script(char)
        if script == "neutral" or script in seen:
            continue
        seen.append(script)
    if not seen and text.strip():
        return ["latin"]
    return seen


def split_text_by_script(text: str) -> list[SpeechSegment]:
    if not text.strip():
        return []

    segments: list[SpeechSegment] = []
    current_script: str | None = None
    current_chars: list[str] = []
    leading_neutral: list[str] = []

    for char in text:
        script = _char_script(char)
        if script == "neutral":
            if current_chars:
                current_chars.append(char)
            else:
                leading_neutral.append(char)
            continue

        if current_script is None:
            current_script = script
            current_chars = leading_neutral + [char]
            leading_neutral = []
            continue

        if script == current_script:
            current_chars.append(char)
            continue

        chunk = "".join(current_chars).strip()
        if chunk:
            segments.append(SpeechSegment(script=current_script, text=chunk))
        current_script = script
        current_chars = leading_neutral + [char]
        leading_neutral = []

    trailing = "".join(current_chars or leading_neutral).strip()
    if trailing:
        segments.append(SpeechSegment(script=current_script or "latin", text=trailing))
    return segments
