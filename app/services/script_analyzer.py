import json
from services.gemini_service import GeminiService

class ScriptAnalyzerService:
    def __init__(self):
        self.gemini = GeminiService()

    async def analyze_script(self, script: str) -> dict:
        prompt = f"""
You are an expert script analyzer for video production.
Analyze the following script and extract structured metadata, breaking it down into scenes.

SCRIPT:
{script}

Instructions:
1. Identify all characters, overall language, narration styles, and general emotion/tone.
2. Break down the script into distinct scenes based on context, location, or pacing changes.
3. Assign a unique ID to each character (e.g., 'char001') and each scene (e.g., 'scene001').
4. Estimate the duration (in seconds) for each scene based on the length and pacing of the dialogue/narration.
5. Provide the output strictly as a valid JSON object without markdown formatting.

JSON SCHEMA:
{{
  "language": "ISO 639-1 code (e.g., 'ko', 'en', 'ja')",
  "genre": "Script genre (e.g., drama, comedy, education)",
  "estimated_duration": 120,
  "scene_count": 5,
  "global_mood": "Overall mood of the script",
  "recommended_voice_style": "Brief recommendation for voice style",
  "recommended_music_style": "Brief recommendation for background music",
  "characters": [
    {{
      "id": "Unique identifier (e.g., 'char001')",
      "name": "Character's name or role",
      "gender": "male, female, or neutral",
      "age_group": "child, young, adult, or senior",
      "emotion": "Dominant emotion",
      "tone": "Voice tone",
      "role_importance": "main, supporting, or background"
    }}
  ],
  "narration": {{
    "exists": true or false,
    "style": "Description of narration style",
    "tone": "Tone of narration",
    "emotion": "Emotion of narrator"
  }},
  "scenes": [
    {{
      "id": "Unique scene ID (e.g., 'scene001')",
      "order": 1,
      "summary": "Brief summary of the scene",
      "script_text": "The exact script lines spoken in this scene",
      "estimated_seconds": 15,
      "emotion": "Dominant emotion of the scene",
      "visual_prompt_hint": "A visual prompt hint for image/video generation",
      "tts_hint": {{
        "speaker_id": "Must match a character.id or 'narrator'",
        "tone": "Voice tone for TTS",
        "speed": "slow, medium, fast"
      }},
      "transition_hint": "cut, crossfade, fade_in, etc."
    }}
  ],
  "analysis_result": {{
    "summary": "1-2 sentence overall summary of the script",
    "error": false
  }}
}}
"""
        try:
            response_text = await self.gemini.generate_text(
                prompt=prompt,
                temperature=0.3,
                task_type="text_gen"
            )
            
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            return json.loads(response_text)
        except Exception as e:
            print(f"[ScriptAnalyzer] Failed to analyze script: {e}")
            return {
                "language": "unknown",
                "genre": "unknown",
                "estimated_duration": 0,
                "scene_count": 0,
                "global_mood": "unknown",
                "recommended_voice_style": "none",
                "recommended_music_style": "none",
                "characters": [],
                "narration": {
                    "exists": False,
                    "style": "none",
                    "tone": "none",
                    "emotion": "none"
                },
                "scenes": [],
                "analysis_result": {
                    "summary": "Analysis failed",
                    "error": True
                },
                "error": str(e)
            }

script_analyzer_service = ScriptAnalyzerService()
