# Local worker settings

The unified worker at `http://127.0.0.1:3004/` owns the inline “제작 설정 · 영상 모델/API” panel. It mounts the existing production components inside the worker page; it does not open or embed another website.

Select a project to edit its production method, PSD/AE preparation, automation, timeline, comic mode, or account-scoped video provider settings. Production settings use the existing validators, preserve other project payload fields, and compare the loaded version before saving. Submitted projects remain locked. Saving settings does not submit a project or approve output.

The local adapter allows only the required settings, media and preparation endpoints. The Host, Origin and per-process local token protect writes. Media uploads pass through loopback so storage CORS does not need to allow localhost. Service credentials remain in the backend.

The video provider vault remains on the production settings API. If the configured local authentication cannot read it, connect the project account using the inline password/PIN form. Passwords are never retained; the returned session stays in the worker process and is cleared when the worker stops. Neither provider secrets nor the vault encryption key are copied into the browser, project payload or local environment.

The script worker at `http://127.0.0.1:3003/` owns “대본 설정” and the existing guideline review page. Defaults are stored under the worker-specific `codex_script_defaults_…` global-settings key. New jobs inherit defaults only for omitted fields; explicit values, including `false`, take precedence. Existing scripts and active jobs are unchanged. Script work and review translations continue through the local Codex CLI.

After editing shared production components, run `npm run build:worker-settings` from `auth-web/` and commit the generated `worker/local_production_ui/production-settings.js` and `.css`. This is a local UI asset build, not a Windows installer release.

Validation: `node --test tests/local-production-settings-api.cjs` and `node tests/native-worker-settings-browser.cjs` from `auth-web/`; `python -m pytest tests/test_native_worker_settings.py` from the repository root. Browser tests use API fixtures and perform no paid generation.
