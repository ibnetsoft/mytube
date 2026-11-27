"""Stage this job's off-drive image evidence inside the CLI attachment sandbox."""
from pathlib import Path
import hashlib
import shutil
import tempfile


class MotionAttachmentRunner:
    def __init__(self, runner, media_root, attachment_root):
        self.runner = runner
        self.media_root = Path(media_root).resolve()
        self.attachment_root = Path(attachment_root).resolve()

    def __getattr__(self, name):
        return getattr(self.runner, name)

    def _stage(self, job_id, stage, context, task, *args, **kwargs):
        context = dict(context)
        paths = []
        for original in context.get('_local_image_paths', []):
            source = Path(original).resolve(strict=True)
            if source.is_relative_to(self.media_root) and not source.is_relative_to(self.attachment_root):
                if not source.is_file() or source.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
                    raise ValueError('Invalid motion evidence image')
                with source.open('rb') as stream:
                    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                self.attachment_root.mkdir(parents=True, exist_ok=True)
                target = self.attachment_root / (digest + source.suffix.lower())
                if not target.exists():
                    # Several independent scenes can stage the same original at
                    # once. A shared .tmp path causes Windows sharing violations
                    # and can expose a partially written file to another worker.
                    temporary = None
                    try:
                        with tempfile.NamedTemporaryFile(dir=self.attachment_root, prefix=digest + '.',
                                                         suffix='.tmp', delete=False) as stream:
                            temporary = Path(stream.name)
                            with source.open('rb') as original:
                                shutil.copyfileobj(original, stream)
                        try:
                            temporary.replace(target)
                        except PermissionError:
                            # Another worker may already have atomically published
                            # the same hash while the target is being read.
                            if not target.is_file():
                                raise
                            with target.open('rb') as existing:
                                if hashlib.file_digest(existing, 'sha256').hexdigest() != digest:
                                    raise
                    finally:
                        if temporary is not None:
                            temporary.unlink(missing_ok=True)
                paths.append(str(target))
            else:
                # The underlying runner keeps its existing strict allowlist.
                paths.append(str(source))
        context['_local_image_paths'] = paths
        return self.runner._stage(job_id, stage, context, task, *args, **kwargs)
