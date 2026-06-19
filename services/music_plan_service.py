"""음악 기획 서비스 — Suno 스타일 UI ↔ Gemini 플랜 ↔ ElevenLabs 생성."""
import json
import re
from typing import Any, Dict, List, Optional

import database as db
from services.gemini_service import gemini_service


STYLE_TAG_LIBRARY: Dict[str, List[str]] = {
    "lofi": ["Lo-fi Beat", "Dusty Vinyl", "Soft Piano", "Rain Ambience", "Mellow Drums", "Warm Bass"],
    "japanese_enka": ["Enka Ballad", "Shamisen", "Koto", "Kobushi Vocal", "Showa Mood", "Melancholy"],
    "jazz": ["Smooth Jazz", "Saxophone", "Walking Bass", "Brush Drums", "Late Night", "Coffee Shop"],
    "piano": ["Solo Piano", "Gentle Melody", "Reverb Hall", "Emotional", "Minimal", "Acoustic"],
    "ambient": ["Atmospheric Pad", "Ethereal", "Slow Evolution", "Deep Space", "Meditative", "Drone"],
    "cinematic": ["Orchestral Swell", "Epic Strings", "Tension Build", "Film Score", "Dramatic", "Wide Soundstage"],
    "city_pop": ["City Pop", "Retro Synth", "Funky Bass", "80s Groove", "Neon Night", "Gated Reverb"],
    "acoustic": ["Acoustic Guitar", "Fingerpicking", "Folk", "Organic", "Campfire", "Natural"],
    "default": ["Groovy Drum", "Deep Sub-bass", "Steady Beat", "Warm Pad", "Clean Mix", "Loopable"],
}

GENRE_GUIDE_LIBRARY: Dict[str, str] = {
    "lofi": "lo-fi hip hop with mellow drums, soft keys, warm bass, vinyl texture, and loopable calm ambience",
    "japanese_enka": (
        "Japanese enka style with sentimental Showa-era mood, slow to mid tempo, "
        "pentatonic melodic phrasing, dramatic vibrato-inspired topline, shamisen/koto accents, "
        "warm strings, restrained percussion, and nostalgic melancholy. Keep it original and avoid "
        "artist names or copyrighted song references."
    ),
    "jazz": "smooth jazz with warm saxophone or piano, walking bass, brushed drums, late-night lounge atmosphere",
    "piano": "gentle piano-focused music with clear melodic motifs, soft dynamics, emotional but uncluttered arrangement",
    "ambient": "ambient atmospheric music with evolving pads, spacious reverb, minimal rhythm, meditative pacing",
    "cinematic": "cinematic score with wide soundstage, orchestral colors, emotional build, polished film-like arrangement",
    "city_pop": "retro city-pop inspired groove with funky bass, clean guitar, synth colors, and bright urban night energy",
    "acoustic": "organic acoustic music with fingerpicked guitar, natural room tone, soft percussion, and intimate warmth",
}


class MusicPlanService:
    def _normalize_weighted_values(self, raw: Any, fallback: List[str]) -> List[str]:
        if isinstance(raw, list):
            values = [str(item).strip() for item in raw if str(item).strip()]
            return values or fallback
        if isinstance(raw, dict):
            weighted: List[str] = []
            for key, value in raw.items():
                try:
                    count = max(0, int(value))
                except Exception:
                    count = 0
                weighted.extend([str(key).strip()] * count)
            return weighted or fallback
        if isinstance(raw, str) and raw.strip():
            return [part.strip() for part in raw.split(",") if part.strip()] or fallback
        return fallback

    def _expand_ratio_sequence(self, raw: Any, total: int, fallback: List[str]) -> List[str]:
        values = self._normalize_weighted_values(raw, fallback)
        if not values:
            values = fallback
        sequence: List[str] = []
        while len(sequence) < total:
            sequence.extend(values)
        return sequence[:total]

    def _resolve_duration_sequence(self, music_config: dict, target_count: int, default_duration: int) -> List[int]:
        distribution = music_config.get("duration_distribution") or {}
        sequence = distribution.get("sequence") if isinstance(distribution, dict) else None
        if isinstance(sequence, list) and sequence:
            durations = []
            for item in sequence:
                try:
                    durations.append(max(120, int(item)))
                except Exception:
                    pass
            if durations:
                expanded: List[int] = []
                while len(expanded) < target_count:
                    expanded.extend(durations)
                return expanded[:target_count]

        options = distribution.get("options") if isinstance(distribution, dict) else None
        if isinstance(options, dict) and options:
            expanded: List[int] = []
            for key, value in options.items():
                try:
                    duration = max(120, int(key))
                    count = max(0, int(value))
                    expanded.extend([duration] * count)
                except Exception:
                    continue
            if expanded:
                while len(expanded) < target_count:
                    expanded.extend(expanded)
                return expanded[:target_count]

        return [default_duration] * target_count

    def _coerce_instruments(self, raw: Any, genre: str) -> List[str]:
        if isinstance(raw, list):
            values = [str(item).strip() for item in raw if str(item).strip()]
            if values:
                return values[:8]
        if isinstance(raw, str) and raw.strip():
            values = [part.strip() for part in raw.split(",") if part.strip()]
            if values:
                return values[:8]
        defaults = {
            "lofi": ["soft piano", "warm bass", "dusty drums"],
            "japanese_enka": ["shamisen", "koto", "warm strings"],
            "jazz": ["saxophone", "upright bass", "brush drums"],
            "piano": ["solo piano", "soft pad"],
            "ambient": ["atmospheric pad", "texture drone", "soft piano"],
            "cinematic": ["strings", "piano", "subtle percussion"],
            "city_pop": ["retro synth", "clean guitar", "funk bass"],
            "acoustic": ["acoustic guitar", "soft percussion", "piano"],
        }
        return defaults.get(str(genre or "").strip(), ["soft piano", "warm pad", "steady drums"])

    def _build_track_lyrics(self, music_config: dict, track_title: str, mood: str) -> str:
        lyrics = music_config.get("lyrics") or {}
        vocal_mode = str(music_config.get("vocal_mode") or "instrumental")
        if vocal_mode == "instrumental" or str(lyrics.get("mode") or "instrumental") == "instrumental":
            return ""
        text = str(lyrics.get("text") or "").strip()
        if text:
            return text
        return f"[Verse]\n{track_title}\n{mood}\n\n[Chorus]\nOriginal safe lyrics for {track_title}"

    def genre_display_name(self, genre: str) -> str:
        labels = {
            "lofi": "Lo-fi",
            "japanese_enka": "Japanese Enka",
            "jazz": "Jazz",
            "piano": "Piano",
            "ambient": "Ambient",
            "cinematic": "Cinematic",
            "city_pop": "City Pop",
            "acoustic": "Acoustic",
        }
        return labels.get(str(genre or "").strip(), str(genre or "Music").replace("_", " ").title())

    def genre_guide(self, genre: str) -> str:
        return GENRE_GUIDE_LIBRARY.get(str(genre or "").strip(), GENRE_GUIDE_LIBRARY["lofi"])

    def is_generic_track_title(self, title: str, index: int) -> bool:
        text = str(title or "").strip()
        if not text:
            return True
        patterns = [
            rf"^track\s*0?{index}$",
            rf"^track\s*0?{index}\s*title$",
            rf"^song\s*0?{index}$",
            rf"^music\s*0?{index}$",
        ]
        return any(re.match(pattern, text, re.IGNORECASE) for pattern in patterns)

    def fallback_track_title(self, index: int, topic: str, genre: str, mood: str = "") -> str:
        topic_text = str(topic or "").strip() or self.genre_display_name(genre)
        mood_text = str(mood or "").replace("_", " ").strip()
        templates = [
            "{topic}의 첫 장면 (Opening Scene of {topic_en})",
            "잔잔히 번지는 {topic} (Softly Spreading {topic_en})",
            "{mood} 마음의 길 (A {mood_en} Path Within)",
            "밤을 건너는 {topic} (Crossing the Night with {topic_en})",
            "오래 남는 선율 (Lingering Melody)",
            "따뜻한 여운 (Warm Afterglow)",
            "고요한 흐름 (Quiet Flow)",
            "마지막 빛 (Last Light)",
        ]
        topic_en = re.sub(r"[^A-Za-z0-9 ]+", " ", topic_text).strip() or self.genre_display_name(genre)
        mood_en = re.sub(r"[^A-Za-z0-9 ]+", " ", mood_text).strip() or "Gentle"
        template = templates[(index - 1) % len(templates)]
        return template.format(
            topic=topic_text[:18],
            topic_en=topic_en[:32],
            mood=mood_text[:12] or "잔잔한",
            mood_en=mood_en[:24],
        )

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

        raw_genre = str(music_config.get("genre") or plan.get("genre") or "lofi")
        genre = self.genre_display_name(raw_genre)
        genre_guide = self.genre_guide(raw_genre)
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
            f"Original {genre} music ({genre_guide}), {', '.join(moods)}, {vocal_directive}, "
            f"{style_hint + ', ' if style_hint else ''}"
            "safe for YouTube playlist, no artist names, no copyrighted melody"
        )

        target_count = int(music_config.get("track_count") or 8)
        playlist_duration = int(music_config.get("playlist_duration_seconds") or 3600)
        track_duration = max(180, min(300, playlist_duration // target_count)) if target_count > 0 else 300
        topic = str(music_config.get("playlist_title") or plan.get("playlist_title") or plan.get("topic") or "").strip()
        track_genre_sequence = self._expand_ratio_sequence(
            music_config.get("genre_mix") or music_config.get("genre_distribution"),
            target_count,
            [raw_genre],
        )
        track_vocal_sequence = self._expand_ratio_sequence(
            music_config.get("vocal_mode_sequence") or music_config.get("vocal_mode_distribution"),
            target_count,
            [vocal_mode],
        )
        track_gender_sequence = self._expand_ratio_sequence(
            music_config.get("vocal_gender_distribution") or music_config.get("singer_gender_distribution"),
            target_count,
            [str((music_config.get("advanced") or {}).get("vocal_gender") or "any")],
        )
        lyrics_ratio = int(music_config.get("lyrics_ratio_percent") or 0)
        duration_sequence = self._resolve_duration_sequence(music_config, target_count, track_duration)

        normalized = []
        for index, item in enumerate(tracks, start=1):
            assigned_genre = str(track_genre_sequence[index - 1] or raw_genre)
            assigned_vocal_mode = str(track_vocal_sequence[index - 1] or vocal_mode)
            assigned_gender = str(track_gender_sequence[index - 1] or "any")
            if isinstance(item, str):
                title = item.strip() or f"Track {index:02d}"
                prompt = title
                mood = ""
                item_duration = duration_sequence[index - 1]
            elif isinstance(item, dict):
                title = str(item.get("title") or item.get("name") or f"Track {index:02d}").strip()
                mood = str(item.get("mood") or item.get("style") or "").strip()
                prompt = str(item.get("prompt") or item.get("music_prompt") or "").strip()
                if not prompt:
                    prompt = ", ".join(part for part in [title, mood, plan.get("mood")] if part)
                item_duration = item.get("duration_seconds") or duration_sequence[index - 1]
            else:
                continue
            if self.is_generic_track_title(title, index):
                title = self.fallback_track_title(index, topic, assigned_genre, mood or (moods[(index - 1) % len(moods)] if moods else ""))
                if self.is_generic_track_title(prompt, index):
                    prompt = title
            include_lyrics = assigned_vocal_mode != "instrumental" and lyrics_ratio > 0 and ((index - 1) / max(1, target_count)) < (lyrics_ratio / 100)
            normalized.append({
                "track_index": index - 1,
                "title": title,
                "genre": assigned_genre,
                "mood": mood,
                "prompt": f"{base_directive}. Track concept: {prompt}",
                "duration_seconds": item_duration,
                "instruments": self._coerce_instruments(item.get("instruments") if isinstance(item, dict) else None, assigned_genre),
                "lyrics": self._build_track_lyrics(music_config, title, mood or "") if include_lyrics else "",
                "vocalist_gender": assigned_gender,
                "vocal_mode": assigned_vocal_mode,
                "status": str(item.get("status") or "planned") if isinstance(item, dict) else "planned",
            })

        while len(normalized) < target_count:
            idx = len(normalized) + 1
            assigned_genre = str(track_genre_sequence[idx - 1] or raw_genre)
            assigned_vocal_mode = str(track_vocal_sequence[idx - 1] or vocal_mode)
            assigned_gender = str(track_gender_sequence[idx - 1] or "any")
            base_mood = moods[(idx - 1) % len(moods)] if moods else (plan.get("mood") or "calm cinematic instrumental background music")
            title = self.fallback_track_title(idx, topic, assigned_genre, base_mood)
            include_lyrics = assigned_vocal_mode != "instrumental" and lyrics_ratio > 0 and ((idx - 1) / max(1, target_count)) < (lyrics_ratio / 100)
            normalized.append({
                "track_index": idx - 1,
                "title": title,
                "genre": assigned_genre,
                "mood": base_mood,
                "prompt": f"{base_directive}. Track concept: {title}, {base_mood}, smooth loopable longform playlist track",
                "duration_seconds": duration_sequence[idx - 1],
                "instruments": self._coerce_instruments(None, assigned_genre),
                "lyrics": self._build_track_lyrics(music_config, title, base_mood) if include_lyrics else "",
                "vocalist_gender": assigned_gender,
                "vocal_mode": assigned_vocal_mode,
                "status": "planned",
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
                        plan["tracks"] = self.coerce_tracks(plan, music_config)
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

        genre_key = music_config.get('genre', 'lofi')
        genre_name = self.genre_display_name(str(genre_key))
        genre_guide = self.genre_guide(str(genre_key))

        prompt = f"""Create a production JSON plan for a longform YouTube music playlist.

Topic: {topic}
Creative brief:
{brief[:3000]}

Requirements:
- Music genre/category: {genre_name} ({genre_key})
- Genre-specific direction: {genre_guide}
- Moods: {moods_str}
- Vocal mode: {music_config.get('vocal_mode', 'instrumental')}
- Target language/market: {music_config.get('target_language', 'global')}
- Track count: {music_config.get('track_count', 8)}
- Total target duration seconds: {music_config.get('playlist_duration_seconds', 3600)}
- Instrumental-first unless brief requests vocals. Avoid artist names, song names, and copyrighted lyrics.
- Each track prompt must be safe for AI music generation and distinct enough for a playlist.
- Create exactly the requested number of tracks.
- Every track must have a meaningful Korean title plus an English subtitle in parentheses. Never use generic names like "Track 01" or "Track 02".

Return JSON only:
{{
  "playlist_title": "...",
  "genre": "{genre_key}",
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
        db.replace_music_track_plans(project_id, plan.get("tracks") or [])
        if music_config is not None:
            self.save_config(project_id, music_config)

    def get_track_plans(self, project_id: int) -> List[Dict[str, Any]]:
        return db.get_music_track_plans(project_id)

    def get_plan(self, project_id: int) -> Optional[dict]:
        settings = db.get_project_settings(project_id) or {}
        raw_plan = settings.get("longform_music_plan_json")
        if not raw_plan:
            return None
        try:
            plan = json.loads(raw_plan)
            if not isinstance(plan, dict):
                return None
            music_config = self.parse_music_config(settings.get("longform_music"))
            if plan.get("tracks"):
                plan["tracks"] = self.coerce_tracks(plan, music_config)
            return plan
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
