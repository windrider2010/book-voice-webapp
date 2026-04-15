from __future__ import annotations

from dataclasses import dataclass
import re


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


def split_text_into_paragraphs(text: str, *, max_chars: int = 360) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []

    normalized = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"(?<=\w)-\n(?=\w)", "", normalized)
    blocks = [_normalize_paragraph_block(block) for block in re.split(r"\n\s*\n+", normalized)]
    paragraphs = [block for block in blocks if block]
    if not paragraphs:
        paragraphs = [_normalize_paragraph_block(normalized)]

    chunks: list[str] = []
    for paragraph in paragraphs:
        chunks.extend(_split_long_paragraph(paragraph, max_chars=max_chars))
    return [chunk for chunk in chunks if chunk]


def _normalize_paragraph_block(block: str) -> str:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _split_long_paragraph(paragraph: str, *, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]

    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?。！？])\s+", paragraph) if sentence.strip()]
    if len(sentences) <= 1:
        return _pack_words(paragraph.split(), max_chars=max_chars)

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = sentence if not current else f"{current} {sentence}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(sentence) <= max_chars:
            current = sentence
        else:
            chunks.extend(_pack_words(sentence.split(), max_chars=max_chars))
            current = ""

    if current:
        chunks.append(current)
    return chunks


def _pack_words(words: list[str], *, max_chars: int) -> list[str]:
    if not words:
        return []

    chunks: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        chunks.append(current)
        current = word
    if current:
        chunks.append(current)
    return chunks
