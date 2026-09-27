"""Run a single H.264 export in the installed Adobe Media Encoder app."""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from adobe_tools import find_media_encoder


class AmeBridgeError(RuntimeError):
    pass


def _jsx_string(path: Path) -> str:
    return json.dumps(str(path.resolve()).replace('\\', '/'), ensure_ascii=True)


def write_script(source: Path, preset: Path, destination: Path, status: Path, script: Path) -> None:
    """Schedule after AME initializes; report encode completion from its event."""
    values = [_jsx_string(path) for path in (source, preset, destination, status)]
    script.write_text('''// AIR Studio Adobe Media Encoder export bridge.
if (!$._AIR_EXPORT) $._AIR_EXPORT = {};
$._AIR_EXPORT.source = %s;
$._AIR_EXPORT.preset = %s;
$._AIR_EXPORT.destination = %s;
$._AIR_EXPORT.status = %s;
$._AIR_EXPORT.write = function(value) {
  var file = new File($._AIR_EXPORT.status);
  if (file.open("w")) { file.write(value); file.close(); }
};
$._AIR_EXPORT.stop = function() { app.scheduleTask("app.quit()", 5000, false); };
$._AIR_EXPORT.run = function() {
  try {
    var bridge = $._AIR_EXPORT;
    var frontend = app.getFrontend();
    if (!frontend) throw "AME frontend unavailable";
    frontend.addEventListener("onBatchItemCreationFailed", function(event) {
      bridge.write("error|batch item: " + event.error);
      bridge.stop();
    });
    var item = frontend.addFileToBatch(new File(bridge.source).fsName, "H.264",
      new File(bridge.preset).fsName, new Folder(bridge.destination).fsName);
    if (!item) throw "AME rejected batch item";
    var host = app.getEncoderHost();
    if (!host) throw "AME encoder host unavailable";
    host.addEventListener("onItemEncodeComplete", function(event) {
      if (String(event.result) == "True") bridge.write("complete|" + event.outputFilePath);
      else bridge.write("error|encode failed: " + event.outputFilePath);
      bridge.stop();
    });
    bridge.write("queued");
    app.scheduleTask("app.getEncoderHost().runBatch()", 5000, false);
  } catch (error) {
    $._AIR_EXPORT.write("error|" + String(error));
    $._AIR_EXPORT.stop();
  }
};
$._AIR_EXPORT.write("scheduled");
app.scheduleTask("$._AIR_EXPORT.run()", 10000, false);
''' % tuple(values), encoding='utf-8')


def _ame_running() -> bool:
    if os.name != 'nt':
        return False
    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Adobe Media Encoder.exe', '/FO', 'CSV', '/NH'],
                            capture_output=True, text=True, errors='replace', timeout=15)
    return 'Adobe Media Encoder.exe' in result.stdout


def export(source: Path, preset: Path, output_dir: Path, status: Path, script: Path,
           *, timeout_seconds: int = 3600) -> Path:
    executable = find_media_encoder()
    if not executable or not executable.is_file():
        raise AmeBridgeError('Adobe Media Encoder executable was not found')
    if _ame_running():
        raise AmeBridgeError('Adobe Media Encoder is already running; close it before automatic export')
    if not source.is_file() or not preset.is_file():
        raise AmeBridgeError('Source media or H.264 preset is missing')
    output_dir.mkdir(parents=True, exist_ok=True)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.unlink(missing_ok=True)
    write_script(source, preset, output_dir, status, script)
    process = subprocess.Popen([str(executable), '--console', 'es.processFile', str(script)], cwd=str(executable.parent))
    deadline = time.monotonic() + timeout_seconds
    try:
        while time.monotonic() < deadline:
            if status.is_file():
                message = status.read_text(encoding='utf-8', errors='replace').strip()
                if message.startswith('error|'):
                    raise AmeBridgeError(message[6:])
                if message.startswith('complete|'):
                    output = output_dir / (source.stem + '.mp4')
                    if output.is_file() and output.stat().st_size >= 1024:
                        return output
                    raise AmeBridgeError('AME reported completion without a valid MP4')
            if process.poll() is not None:
                raise AmeBridgeError(f'AME exited before export completion (code {process.returncode})')
            time.sleep(1)
        raise AmeBridgeError(f'AME export timed out after {timeout_seconds}s')
    finally:
        if process.poll() is None:
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=15)
