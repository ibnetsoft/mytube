# Editable thumbnail contract

Applies to every future Codex-worker thumbnail, every category, and manual Codex repairs.

1. Generate only a **text-free background** with the built-in image tool. Do not ask the image model to draw headlines or create a second flattened final.
2. Save chosen headline/subheadline as `thumbnail_design.text_layers`, separately from the three alternative `thumbnail_hook_texts`. Alternatives are not automatically stacked together.
3. Store the durable raw background in `thumbnail_bg_url`, `thumbnail_design.editor_bg_url`, and `thumbnail_design.bg_url`. Never persist `blob:` URLs.
4. A prepared background is not a confirmed thumbnail: `thumbnail_completed=false`, `thumbnail_url=null`, and `render_status=awaiting_user_save`.
5. The user edits text, font, color, size, stroke, and position on the thumbnail page. Preview and Save use the same canvas renderer (480-wide editor units, 1280×720 output; fonts loaded before drawing).
6. Only **Save** renders and uploads the final PNG. Persist that separate URL plus the raw background and editable layers; set completion only after persistence succeeds. Reopening uses the raw background, never the flattened final.
7. Failed background loading must show an error. No implicit substitution with scene 1 or any other image. Missing background requires generation/upload or an explicit user choice.
8. Background revisions use content-addressed object paths. Do not overwrite a user's confirmed design, submitted project, or independently revised script when syncing worker results. Never copy another project's media.

The existing one-off 3197 package is preserved. It is not a template for generating future flattened final images. No SQL schema change is needed: the editable contract lives in existing JSON payloads.
