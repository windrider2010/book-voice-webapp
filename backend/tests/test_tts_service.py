from __future__ import annotations

from types import SimpleNamespace

from app.services import tts_service


def test_kokoro_pipeline_uses_explicit_repo_and_zh_warmup(monkeypatch) -> None:
    tts_service._PIPELINES.clear()
    created: list[dict[str, object]] = []
    calls: list[tuple[str, str]] = []

    class FakePipeline:
        def __init__(self, *, lang_code: str, repo_id: str, device: str) -> None:
            created.append(
                {
                    "lang_code": lang_code,
                    "repo_id": repo_id,
                    "device": device,
                }
            )
            self.lang_code = lang_code

        def __call__(self, text: str, *, voice: str, speed: float):
            calls.append((self.lang_code, text))
            return [SimpleNamespace(audio=[0.0, 0.0])]

    monkeypatch.setitem(__import__("sys").modules, "kokoro", SimpleNamespace(KPipeline=FakePipeline))

    service = tts_service.KokoroTtsService(
        default_en_voice="af_heart",
        default_zh_voice="zf_xiaobei",
        device="cpu",
    )

    service.preload()

    assert created == [
        {"lang_code": "a", "repo_id": "hexgrad/Kokoro-82M", "device": "cpu"},
        {"lang_code": "z", "repo_id": "hexgrad/Kokoro-82M", "device": "cpu"},
    ]
    assert calls == [("a", "Hello."), ("z", "你好。")]
