from pathlib import Path


TEMPLATE = Path("templates/pages/tts.html")


def test_tts_page_restores_persisted_audio_on_initial_load_and_project_switch():
    source = TEMPLATE.read_text(encoding="utf-8")

    assert "await restoreProjectTts(pid);" in source
    assert "function applyPersistedTts(ttsData)" in source
    assert "function clearPersistedTtsUi()" in source
    assert "window.addEventListener('projectStateCleared'" in source
    assert "applyPersistedTts(data.tts || null);" in source
