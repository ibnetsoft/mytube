"""Persistent-worker Gemini web narration, without an AIR browser extension.

Dedicated automated Chrome sign-in was rejected by Google in live testing.
The setup command fails explicitly until a supported worker connection exists.
Never copies cookies from the user's daily profile.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import time
import uuid

from worker.cowork_narration import prepare, accept, assemble, generate_dialogue, load_manifest

ROOT = Path(__file__).resolve().parents[1]


def profile_path() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "AIRStudio/AIRWorker/gemini-browser"


@contextmanager
def browser_lock():
    profile = profile_path()
    profile.mkdir(parents=True, exist_ok=True)
    # OS lock is released on crashes; never steal a profile from a live process.
    with (profile / "air-worker.lock").open("a+b") as handle:
        handle.seek(0)
        if handle.read(1) == b"":
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("Gemini worker browser is already in use") from exc
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield profile
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def split_script(script: str, dialogue_voice: str = "", limit: int = 1200) -> list[dict]:
    """Quoted speech uses the configured voice; narration is never paid TTS.

    Explicit audio_segments can be supplied for multiple character voices.
    Only paired double/curly quotes denote speech in this default adapter.
    """
    segments = []
    def narration(text):
        text = text.strip()
        while text:
            end = min(len(text), limit)
            if len(text) > limit:
                boundary = max(text.rfind(". ", 0, limit), text.rfind("다.\n", 0, limit), text.rfind("\n", 0, limit))
                if boundary < 0:
                    boundary = text.rfind(" ", 0, limit)
                end = boundary + 1 if boundary >= 0 else limit
            segments.append({"kind": "narration", "text": text[:end].strip()})
            text = text[end:].strip()
    cursor = 0
    for match in re.finditer(r'“([^”]+)”|"([^"\n]+)"', script):
        narration(script[cursor:match.start()])
        if not dialogue_voice:
            raise ValueError("Direct speech needs GEMINI_DIALOGUE_VOICE_ID or explicit audio_segments with voice_id")
        segments.append({"kind": "dialogue", "text": match.group(1) or match.group(2), "voice_id": dialogue_voice})
        cursor = match.end()
    narration(script[cursor:])
    return segments


# Instrument only the explicit read-aloud operation in the worker-owned tab.
# No Gemini private endpoints, authentication headers, or cookies are exported.
AUDIO_HOOK = r"""
(() => {
  const original = HTMLMediaElement.prototype.play;
  const originalFetch = window.fetch.bind(window);
  window.__airAudioJob = null;
  HTMLMediaElement.prototype.play = function(...args) {
    const job = window.__airAudioJob;
    if (job && !job.claimed && this instanceof HTMLAudioElement) {
      job.claimed = true;
      const media = this;
      const source = media.currentSrc || media.src;
      const data = (async () => {
        if (!source.startsWith('blob:') && !source.startsWith('data:audio/'))
          throw Error('Unsupported audio transport: single Blob/data audio required');
        const response = await originalFetch(source);
        const blob = await response.blob();
        if (!blob.size || blob.size > 32000000) throw Error('Invalid audio size');
        return await new Promise((resolve,reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(Error('Cannot read audio'));
          reader.readAsDataURL(blob);
        });
      })().then(value => ({value}), error => ({error: String(error)}));
      const report = payload => {
        if (window.__airAudioJob === job) window.airAudioResult({id:job.id,...payload});
      };
      data.then(result => { if (result.error) report(result); });
      media.addEventListener('error', () => report({error:'Gemini playback failed'}), {once:true});
      media.addEventListener('ended', async () => {
        if ((media.currentSrc || media.src) !== source) report({error:'Audio source changed during playback'});
        else report(await data);
      }, {once:true});
    }
    return Reflect.apply(original, this, args);
  };
})();
"""


def decode_audio_result(payload: dict) -> bytes:
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    value = payload.get("value", "")
    if not isinstance(value, str) or len(value) > 45000000:
        raise ValueError("Invalid audio payload")
    match = re.fullmatch(r"data:(?:audio/[a-zA-Z0-9.+-]+|application/octet-stream)(?:;[^,]*)?;base64,([A-Za-z0-9+/=\r\n]+)", value)
    if not match:
        raise ValueError("Unsupported audio encoding")
    result = base64.b64decode(match.group(1), validate=True)
    if not result:
        raise ValueError("Empty audio")
    return result


class GeminiBrowser:
    def __init__(self, context):
        self.context = context
        self.pending = {}

    async def start(self):
        async def receive(source, payload):
            future = self.pending.get(payload.get("id")) if isinstance(payload, dict) else None
            if not future or future.done() or not source["frame"].url.startswith("https://gemini.google.com/"):
                return
            try:
                future.set_result(decode_audio_result(payload))
            except Exception as exc:
                future.set_exception(exc)
        await self.context.expose_binding("airAudioResult", receive)
        await self.context.add_init_script(AUDIO_HOOK)
        self.page = await self.context.new_page()

    async def generate(self, text: str, target: Path) -> Path:
        page = self.page
        await page.goto("https://gemini.google.com/app", wait_until="domcontentloaded")
        # Anonymous Gemini also exposes the composer and returns text, but has
        # no read-aloud. Composer visibility alone is not authentication proof.
        login = page.get_by_role("button", name=re.compile(r"^(로그인|Sign in)$"))
        login_link = page.get_by_role("link", name=re.compile(r"^(로그인|Sign in)$"))
        if await login.count() and await login.first.is_visible() or await login_link.count() and await login_link.first.is_visible():
            raise RuntimeError("Gemini worker profile is signed out. Automated Chrome sign-in was rejected by Google; this worker connection is not ready. Do not retry setup or change account security settings.")
        editor = page.get_by_role("textbox", name=re.compile("Gemini 프롬프트 입력|Enter a prompt for Gemini"))
        try:
            await editor.wait_for(state="visible", timeout=20000)
        except Exception as exc:
            raise RuntimeError("Gemini worker browser is unavailable or signed out; a supported browser connection is required") from exc
        if (await editor.inner_text()).strip():
            raise RuntimeError("Worker browser has an unsent draft; refusing to overwrite it")
        count = await page.locator("message-content").count()
        await editor.fill("다음 원문만 수정 없이 한 번 출력하세요. 설명, 제목, 인사, 마크다운을 추가하지 마세요.\n\n" + text)
        await page.get_by_role("button", name=re.compile("^(메시지 보내기|Send message|Submit)$")).click()
        await page.wait_for_function("n => document.querySelectorAll('message-content').length > n", arg=count, timeout=90000)
        response = page.locator("message-content").last
        previous, stable = "", 0
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            value = " ".join((await response.inner_text()).split())
            if value != previous:
                previous, stable = value, time.monotonic()
            stopped = await page.get_by_role("button", name=re.compile("대답 생성 중지|Stop response")).count() == 0
            if value and stopped and time.monotonic() - stable > 2:
                break
            await asyncio.sleep(.3)
        else:
            raise RuntimeError("Gemini response timed out")
        if previous != " ".join(text.split()):
            raise RuntimeError("Gemini changed the narration; refusing to use mismatched audio")
        # The response-local menu must not accidentally select a chat sidebar menu.
        more = response.locator("xpath=ancestor::*[.//button[@aria-label='옵션 더보기' or @aria-label='More']][1]").get_by_role("button", name=re.compile("^(옵션 더보기|More)$"))
        await more.click()
        # Gemini's custom menu item does not consistently expose menuitem role.
        listen = page.get_by_text(re.compile("^(듣기|Listen)$")).last
        try:
            await listen.wait_for(state="visible", timeout=5000)
        except Exception:
            await page.screenshot(path=str(target.with_suffix('.diagnostic.png')))
            raise
        job = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self.pending[job] = future
        try:
            await page.evaluate("id => { window.__airAudioJob = {id, claimed:false}; }", job)
            await listen.click()
            audio = await asyncio.wait_for(future, timeout=360)
            target.write_bytes(audio)
            return target
        finally:
            self.pending.pop(job, None)
            if not page.is_closed():
                await page.evaluate("window.__airAudioJob = null")


async def run_audio_stage(package: dict, directory: Path, dialogue_voice: str = "") -> dict:
    script_hash = hashlib.sha256(str(package.get("script") or "").encode()).hexdigest()
    segments = package.get("audio_segments") or split_script(str(package.get("script") or ""), dialogue_voice)
    manifest = directory / "narration.json"
    if manifest.exists():
        previous = load_manifest(manifest)
        expected = [(s["kind"], s["text"].strip(), s.get("voice_id")) for s in segments]
        actual = [(s["kind"], s["text"], s.get("voice_id")) for s in previous["segments"]]
        if expected != actual:
            raise ValueError("Existing audio job belongs to a different script or voice configuration")
    else:
        manifest = prepare(segments, directory)
    from playwright.async_api import async_playwright
    with browser_lock() as profile:
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(str(profile), channel="chrome", headless=False, chromium_sandbox=True)
            try:
                browser = GeminiBrowser(context)
                await browser.start()
                for segment in load_manifest(manifest)["segments"]:
                    if segment["kind"] != "narration" or segment["state"] == "ready":
                        continue
                    source = directory / f"{segment['id']}.download"
                    await browser.generate(segment["text"], source)
                    accept(manifest, segment["id"], source)
            finally:
                await context.close()
    await generate_dialogue(manifest)
    result = assemble(manifest)
    return {"provider": "gemini_web+elevenlabs", "manifest_path": str(manifest.resolve()),
            "audio_path": str((directory / result["output"]).resolve()), "script_sha256": script_hash,
            "duration_seconds": result["duration_seconds"], "timeline": result["timeline"]}


def maybe_generate_audio(package: dict, payload: dict, directory: Path) -> None:
    enabled = payload.get("generate_gemini_narration", os.environ.get("GEMINI_WEB_NARRATION_ENABLED", "0") == "1")
    if enabled is not True:
        return
    if payload.get("audio_segments"):
        package["audio_segments"] = payload["audio_segments"]
    voice = str(payload.get("dialogue_voice_id") or os.environ.get("GEMINI_DIALOGUE_VOICE_ID") or "")
    package["narration_audio"] = asyncio.run(run_audio_stage(package, directory, voice))


async def setup():
    raise RuntimeError(
        "Google rejected sign-in from the automated worker browser. "
        "This setup path is disabled. Keep the existing signed-in Chrome session; "
        "a supported persistent-worker connection has not yet been validated."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["setup", "run"])
    parser.add_argument("--package", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.action == "setup":
        asyncio.run(setup())
    elif args.package and args.out:
        result = asyncio.run(run_audio_stage(json.loads(args.package.read_text(encoding="utf-8-sig")), args.out,
                                             os.environ.get("GEMINI_DIALOGUE_VOICE_ID", "")))
        print(json.dumps(result, ensure_ascii=False))
    else:
        parser.error("run requires --package and --out")
