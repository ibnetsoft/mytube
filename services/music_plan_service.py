"""음악 기획 서비스 — Suno 스타일 UI ↔ Gemini 플랜 ↔ ElevenLabs 생성."""
import json
import re
from typing import Any, Dict, List, Optional

import database as db
from services.gemini_service import gemini_service


STYLE_TAG_LIBRARY: Dict[str, List[str]] = {
    "lofi": ["Lo-fi Beat", "Dusty Vinyl", "Soft Piano", "Rain Ambience", "Mellow Drums", "Warm Bass"],
    "jazz": ["Smooth Jazz", "Saxophone", "Walking Bass", "Brush Drums", "Late Night", "Coffee Shop"],
    "piano": ["Solo Piano", "Gentle Melody", "Reverb Hall", "Emotional", "Minimal", "Acoustic"],
    "ambient": ["Atmospheric Pad", "Ethereal", "Slow Evolution", "Deep Space", "Meditative", "Drone"],
    "cinematic": ["Orchestral Swell", "Epic Strings", "Tension Build", "Film Score", "Dramatic", "Wide Soundstage"],
    "city_pop": ["City Pop", "Retro Synth", "Funky Bass", "80s Groove", "Neon Night", "Gated Reverb"],
    "acoustic": ["Acoustic Guitar", "Fingerpicking", "Folk", "Organic", "Campfire", "Natural"],
    "default": ["Groovy Drum", "Deep Sub-bass", "Steady Beat", "Warm Pad", "Clean Mix", "Loopable"],
}


class MusicPlanService:
    def parse_music_config(self, raw: Any) -> dict:
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return {}

    def build_brief(self, music_config: dict, topic: str = "") -> str:
        parts: List[str] = []
        if topic:
            parts.append(f"Playlist concept: {topic}")

        simple = str(music_config.get("simple_prompt") or "").strip()
        if simple:
            parts.append(simple)

        styles = music_config.get("styles") or {}
        style_prompt = str(styles.get("prompt") or "").strip()
        if style_prompt:
            parts.append(f"Musical style: {style_prompt}")

        tags = styles.get("tags") or []
        if tags:
            parts.append(f"Style tags: {', '.join(tags)}")

        lyrics = music_config.get("lyrics") or {}
        lyrics_mode = str(lyrics.get("mode") or "instrumental")
        lyrics_text = str(lyrics.get("text") or "").strip()
        if lyrics_mode == "instrumental":
            parts.append("Instrumental only, no vocals.")
        elif lyrics_text:
            parts.append(f"Lyrics direction:\n{lyrics_text[:2000]}")
        else:
            parts.append("Original vocals allowed with safe non-copyright lyrics.")

        advanced = music_config.get("advanced") or {}
        weirdness = int(advanced.get("weirdness") or 50)
        influence = int(advanced.get("style_influence") or 50)
        if weirdness >= 70:
            parts.append("Experimental, unconventional arrangement.")
        elif weirdness <= 30:
            parts.append("Safe, conventional, predictable arrangement.")
        if influence >= 70:
            parts.append("Strictly follow the described style.")
        elif influence <= 30:
            parts.append("Loosely inspired by the style, more creative freedom.")

        vocal_gender = str(advanced.get("vocal_gender") or "any")
        if vocal_gender == "male":
            parts.append("Prefer soft male vocals if vocals are used.")
        elif vocal_gender == "female":
            parts.append("Prefer soft female vocals if vocals are used.")

        notes = str(music_config.get("notes") or "").strip()
        if notes:
            parts.append(f"Additional notes: {notes}")

        return "\n".join(parts).strip() or topic or "AI music playlist"

    def coerce_tracks(self, plan: dict, music_config: dict) -> list:
        tracks = plan.get("tracks") if isinstance(plan, dict) else None
        if not isinstance(tracks, list):
            tracks = []

        genre = str(music_config.get("genre") or plan.get("genre") or "lofi").replace("_", " ")
        moods_raw = music_config.get("moods") or plan.get("moods") or [plan.get("mood") or "calm"]
        if isinstance(moods_raw, str):
            moods = [m.strip() for m in moods_raw.split(",") if m.strip()]
        else:
            moods = [str(m).replace("_", " ") for m in moods_raw if m]

        vocal_mode = str(music_config.get("vocal_mode") or "instrumental")
        if vocal_mode == "instrumental":
            vocal_directive = "no vocals, instrumental only"
        elif vocal_mode == "soft_vocal":
            vocal_directive = "soft subtle vocals allowed, no copyrighted lyrics"
        else:
            vocal_directive = "original vocals allowed, no copyrighted lyrics"

        styles = music_config.get("styles") or {}
        style_hint = str(styles.get("prompt") or "").strip()
        base_directive = (
            f"Original {genre} music, {', '.join(moods)}, {vocal_directive}, "
            f"{style_hint + ', ' if style_hint else ''}"
            "safe for YouTube playlist, no artist names, no copyrighted melody"
        )

        target_count = int(music_config.get("track_count") or 8)
        playlist_duration = int(music_config.get("playlist_duration_seconds") or 3600)
        track_duration = max(180, min(300, playlist_duration // target_count)) if target_count > 0 else 300

        normalized = []
        for index, item in enumerate(tracks, start=1):
            if isinstance(item, str):
                title = item.strip() or f"Track {index:02d}"
                prompt = title
                mood = ""
            elif isinstance(item, dict):
                title = str(item.get("title") or item.get("name") or f"Track {index:02d}").strip()
                mood = str(item.get("mood") or item.get("style") or "").strip()
                prompt = str(item.get("prompt") or item.get("music_prompt") or "").strip()
                if not prompt:
                    prompt = ", ".join(part for part in [title, mood, plan.get("mood")] if part)
            else:
                continue
            normalized.append({
                "title": title,
                "mood": mood,
                "prompt": f"{base_directive}. Track concept: {prompt}",
                "duration_seconds": item.get("duration_seconds") or track_duration,
            })

        while len(normalized) < target_count:
            idx = len(normalized) + 1
            base_mood = plan.get("mood") or "calm cinematic instrumental background music"
            normalized.append({
                "title": f"Track {idx:02d}",
                "mood": base_mood,
                "prompt": f"{base_directive}. Track concept: {base_mood}, smooth loopable longform playlist track",
                "duration_seconds": track_duration,
            })
        return normalized[:target_count]

    def _gemini_temperature(self, music_config: dict) -> float:
        advanced = music_config.get("advanced") or {}
        weirdness = int(advanced.get("weirdness") or 50)
        return round(0.3 + (weirdness / 100) * 0.6, 2)

    async def generate_plan(
        self,
        project_id: int,
        music_config: dict,
        *,
        force_regenerate: bool = False,
    ) -> dict:
        settings = db.get_project_settings(project_id) or {}
        music_config = dict(music_config or {})

        if not force_regenerate:
            raw_plan = settings.get("longform_music_plan_json")
            if raw_plan:
                try:
                    plan = json.loads(raw_plan)
                    if isinstance(plan, dict) and plan.get("tracks"):
                        return plan
                except Exception:
                    pass

        project = db.get_project(project_id) or {}
        topic = (
            str(music_config.get("playlist_title") or "").strip()
            or project.get("topic")
            or "AI music playlist"
        )
        brief = self.build_brief(music_config, topic)

        moods = music_config.get("moods", ["calm"])
        if isinstance(moods, list):
            moods_str = ", ".join(moods)
        else:
            moods_str = str(moods)

        prompt = f"""Create a production JSON plan for a longform YouTube music playlist.

Topic: {topic}
Creative brief:
{brief[:3000]}

Requirements:
- Music genre/category: {music_config.get('genre', 'lofi')}
- Moods: {moods_str}
- Vocal mode: {music_config.get('vocal_mode', 'instrumental')}
- Target language/market: {music_config.get('target_language', 'global')}
- Track count: {music_config.get('track_count', 8)}
- Total target duration seconds: {music_config.get('playlist_duration_seconds', 3600)}
- Instrumental-first unless brief requests vocals. Avoid artist names, song names, and copyrighted lyrics.
- Each track prompt must be safe for AI music generation and distinct enough for a playlist.

Return JSON only:
{{
  "playlist_title": "...",
  "genre": "{music_config.get('genre', 'lofi')}",
  "moods": [],
  "mood": "...",
  "visual_concept": "...",
  "thumbnail_concept": "...",
  "description_angle": "...",
  "tracks": [
    {{"title": "...", "mood": "...", "prompt": "..."}}
  ]
}}"""

        plan: dict = {}
        try:
            text = await gemini_service.generate_text(
                prompt,
                temperature=self._gemini_temperature(music_config),
                project_id=project_id,
                task_type="music_planning",
            )
            match = re.search(r"\{[\s\S]*\}", text or "")
            if match:
                plan = json.loads(match.group())
        except Exception as e:
            print(f"[MusicPlan] Failed to generate plan: {e}")
            plan = {}

        plan.setdefault("playlist_title", topic)
        plan.setdefault("genre", music_config.get("genre", "lofi"))
        plan.setdefault("moods", music_config.get("moods", ["calm"]))
        plan.setdefault("mood", "calm cinematic instrumental background music")
        plan.setdefault(
            "visual_concept",
            f"cinematic YouTube playlist cover for {topic}, atmospheric, clean, premium, 16:9",
        )
        plan["tracks"] = self.coerce_tracks(plan, music_config)
        return plan

    def save_config(self, project_id: int, music_config: dict) -> None:
        db.update_project_setting(project_id, "longform_music", json.dumps(music_config, ensure_ascii=False))

    def save_plan(self, project_id: int, plan: dict, music_config: Optional[dict] = None) -> None:
        db.update_project_setting(project_id, "longform_music_plan_json", json.dumps(plan, ensure_ascii=False))
        if music_config is not None:
            self.save_config(project_id, music_config)

    def get_plan(self, project_id: int) -> Optional[dict]:
        settings = db.get_project_settings(project_id) or {}
        raw_plan = settings.get("longform_music_plan_json")
        if not raw_plan:
            return None
        try:
            plan = json.loads(raw_plan)
            return plan if isinstance(plan, dict) else None
        except Exception:
            return None

    def get_style_tags(self, genre: str) -> List[str]:
        return list(STYLE_TAG_LIBRARY.get(genre) or STYLE_TAG_LIBRARY["default"])

    async def suggest_styles(self, topic: str, genre: str = "lofi", language: str = "ko") -> dict:
        prompt = f"""Suggest a music style description for an AI music playlist.

Topic: {topic}
Genre: {genre}
Language for output: {language}

Return JSON only:
{{
  "prompt": "one paragraph style description mixing genre, instruments, mood, tempo",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6"]
}}

Rules:
- No artist names or copyrighted song references.
- Tags should be short (2-4 words each).
- Make it suitable for YouTube background music playlists."""
        text = await gemini_service.generate_text(prompt, temperature=0.7, task_type="music_planning")
        match = re.search(r"\{[\s\S]*\}", text or "")
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {"prompt": text or "", "tags": self.get_style_tags(genre)}

    async def suggest_lyrics(self, topic: str, style_prompt: str = "", language: str = "ko") -> str:
        prompt = f"""Write original safe lyrics for an AI music track.

Topic: {topic}
Style: {style_prompt}
Language: {language}

Use section tags like [Verse], [Chorus], [Bridge].
No copyrighted lyrics, no artist references.
Return lyrics only."""
        return (await gemini_service.generate_text(prompt, temperature=0.8, task_type="music_planning")) or ""


music_plan_service = MusicPlanService()
