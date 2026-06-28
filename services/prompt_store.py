from pathlib import Path


class PromptStore:
    def __init__(self) -> None:
        self.base_dir = Path(__file__).resolve().parent.parent / "prompts" / "longform"

    def get_wrapper(self, domain: str, provider: str) -> str:
        provider_key = (provider or "gemini").strip().lower()
        path = self.base_dir / domain / f"{provider_key}.md"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        fallback = self.base_dir / domain / "gemini.md"
        if fallback.exists():
            return fallback.read_text(encoding="utf-8").strip()
        return ""

    def build_prompt(self, domain: str, provider: str, base_prompt: str) -> str:
        wrapper = self.get_wrapper(domain, provider)
        if wrapper:
            return f"{wrapper}\n\n{base_prompt}".strip()
        return base_prompt


prompt_store = PromptStore()
