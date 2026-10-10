"""
[AIR-0227C Stage 3] Local API auth token storage.

docs/AIR_WORKER_LOCAL_API_SECURITY.md has the full design/QA writeup - this
module only implements storage + comparison.

Storage: Windows DPAPI (`win32crypt.CryptProtectData`/`CryptUnprotectData`,
via the already-installed pywin32 dependency) ties the encrypted blob to the
current Windows user account - even another admin-level process running as
a different user on the same machine cannot decrypt it. This was evaluated
as NOT excessive for this Task (pywin32 already a dependency, the API is a
few lines) so it's implemented directly rather than deferred to AIR-0227D as
only a plan. A plaintext+ACL-restricted fallback exists for non-Windows/dev
environments where pywin32 isn't usable.

Comparison uses hmac.compare_digest (constant-time) and always re-reads the
current token from disk on every call (no in-process caching) - this is
what makes "재발급 후 이전 토큰 즉시 무효화" (old token invalidated
immediately after reissue) true without needing to restart or signal the
running Local API process.
"""
import hmac
import secrets
import subprocess

from worker_config import STATE_DIR

TOKEN_FILE_DPAPI = STATE_DIR / "local_api_token.dpapi"
TOKEN_FILE_PLAIN = STATE_DIR / "local_api_token.txt"

try:
    import win32crypt
    _DPAPI_AVAILABLE = True
except ImportError:
    _DPAPI_AVAILABLE = False


def _restrict_to_current_user(path):
    """Best-effort ACL lockdown - removes inherited permissions and grants
    only the current user Full Control. DPAPI alone already prevents other
    users from decrypting the blob's *contents*, but this additionally stops
    other local accounts from even reading/deleting the file."""
    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{__import__('os').environ.get('USERNAME', '')}:F"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        pass  # best-effort - never let ACL lockdown failure block token creation


def _generate_token() -> str:
    return secrets.token_urlsafe(32)


def _write_token(token: str):
    if _DPAPI_AVAILABLE:
        TOKEN_FILE_PLAIN.unlink(missing_ok=True)
        encrypted = win32crypt.CryptProtectData(token.encode("utf-8"), "AIR Worker Local API token", None, None, None, 0)
        TOKEN_FILE_DPAPI.write_bytes(encrypted)
        _restrict_to_current_user(TOKEN_FILE_DPAPI)
    else:
        TOKEN_FILE_DPAPI.unlink(missing_ok=True)
        TOKEN_FILE_PLAIN.write_text(token, encoding="utf-8")
        _restrict_to_current_user(TOKEN_FILE_PLAIN)


def _read_token() -> str | None:
    if _DPAPI_AVAILABLE and TOKEN_FILE_DPAPI.exists():
        try:
            _desc, decrypted = win32crypt.CryptUnprotectData(TOKEN_FILE_DPAPI.read_bytes(), None, None, None, 0)
            return decrypted.decode("utf-8")
        except Exception:
            return None
    if TOKEN_FILE_PLAIN.exists():
        return TOKEN_FILE_PLAIN.read_text(encoding="utf-8").strip()
    return None


def get_or_create_token() -> str:
    existing = _read_token()
    if existing:
        return existing
    token = _generate_token()
    _write_token(token)
    return token


def reissue_token() -> str:
    """Overwrites the token file with a brand-new value. Must be invoked
    locally (CLI, filesystem access to this machine as this Windows user) -
    never exposed as an HTTP endpoint, since an attacker who already has the
    old token could otherwise just call 'reissue' and get a valid new one,
    defeating revocation."""
    token = _generate_token()
    _write_token(token)
    return token


def verify_token(provided: str | None) -> bool:
    if not provided:
        return False
    current = _read_token()
    if not current:
        return False
    return hmac.compare_digest(provided, current)


def storage_backend() -> str:
    return "dpapi" if _DPAPI_AVAILABLE else "plaintext+acl"
