"""Persist version-checked AE inputs across polling passes and worker restarts."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path


def load_candidates(request, base_url, headers, source, limit, cache_dir):
    namespace = hashlib.sha256(base_url.encode()).hexdigest()[:16]
    directory = Path(cache_dir) / namespace / source
    directory.mkdir(parents=True, exist_ok=True)
    manifest = request("POST", base_url + "/rest/v1/rpc/std_ae_candidate_manifest", headers,
                       json={"p_source": source, "p_limit": max(1, min(100, int(limit)))}).json()
    if not isinstance(manifest, list):
        raise RuntimeError("Invalid AE candidate manifest")
    rows, missing = {}, []
    def location(identity):
        return directory / (hashlib.sha256(str(identity).encode()).hexdigest() + ".json")
    for item in manifest:
        identity = str(item["id"])
        try:
            cached = json.loads(location(identity).read_text(encoding="utf-8"))
            if item.get("version") and cached.get("version") == item["version"]:
                rows[identity] = cached
                continue
        except (OSError, ValueError, AttributeError):
            pass
        missing.append(identity)
    if missing:
        fresh = request("POST", base_url + "/rest/v1/rpc/std_ae_candidate_payloads", headers,
                        json={"p_source": source, "p_ids": missing}).json()
        if not isinstance(fresh, list):
            raise RuntimeError("Invalid AE candidate payloads")
        for row in fresh:
            identity = str(row["id"])
            if identity not in missing or not row.get("version"):
                raise RuntimeError("Invalid AE candidate version")
            rows[identity] = row
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as handle:
                json.dump(row, handle, ensure_ascii=False)
                temporary = handle.name
            os.replace(temporary, location(identity))
    if any(str(item["id"]) not in rows for item in manifest):
        raise RuntimeError("AE candidate changed while loading; retry the next polling pass")
    # Titles/status are always fresh even when only metadata changed.
    return [{**rows[str(item["id"])], **{k: v for k, v in item.items() if k != "version"}}
            for item in manifest]
