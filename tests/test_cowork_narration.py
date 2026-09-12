import hashlib
import wave

import pytest

from worker.cowork_narration import prepare, load_manifest, save_manifest, assemble


def test_dialogue_requires_explicit_voice(tmp_path):
    with pytest.raises(ValueError, match="voice_id"):
        prepare([{"kind": "dialogue", "text": "안녕"}], tmp_path / "job")


def test_incomplete_audio_cannot_be_assembled(tmp_path):
    path = prepare([{"kind": "narration", "text": "아침이었다."}], tmp_path / "job")
    with pytest.raises(ValueError, match="ready"):
        assemble(path)
    assert not (path.parent / "narration-mixed.wav").exists()


def test_mixed_audio_preserves_order_and_exact_sample_timing(tmp_path):
    path = prepare([{"kind": "narration", "text": "문이 열렸다."},
                    {"kind": "dialogue", "text": "누구세요?", "voice_id": "test"},
                    {"kind": "narration", "text": "대답은 없었다."}], tmp_path / "job")
    data = load_manifest(path)
    for index, segment in enumerate(data["segments"], 1):
        audio = path.parent / f"{segment['id']}.wav"
        with wave.open(str(audio), "wb") as output:
            output.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
            output.writeframes(index.to_bytes(2, "little") * (index * 4800))
        segment.update(state="ready", file=audio.name, sha256=hashlib.sha256(audio.read_bytes()).hexdigest())
    save_manifest(path, data)
    result = assemble(path)
    assert [s["start"] for s in result["timeline"]] == [0, .1, .3]
    assert result["duration_seconds"] == .6
    with wave.open(str(path.parent / result["output"]), "rb") as output:
        assert output.readframes(1) == b'\x01\x00'
        output.setpos(4800)
        assert output.readframes(1) == b'\x02\x00'
    changed = path.parent / data["segments"][0]["file"]
    changed.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        assemble(path)
