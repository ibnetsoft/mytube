import json
from services.gemini_service import GeminiService

class ScriptAnalyzerService:
    def __init__(self):
        self.gemini = GeminiService()

    async def analyze_script(self, script: str) -> dict:
        prompt = f"""
You are an expert script analyzer for video production.
Analyze the following script and extract structured metadata.

SCRIPT:
{script}

Instructions:
Identify all characters, overall language, narration styles, and general emotion/tone.
Return the result strictly as a valid JSON object without markdown formatting.

JSON SCHEMA:
{{
  "language": "ISO 639-1 code (e.g., 'ko', 'en', 'ja')",
  "characters": [
    {{
      "name": "Character's name or role (e.g., 'Hero', 'Narrator')",
      "gender": "male, female, or neutral",
      "age_group": "child, young, adult, or senior",
      "emotion": "Dominant emotion (e.g., angry, happy, calm)",
      "tone": "Voice tone (e.g., confident, soft, energetic)",
      "role_importance": "main, supporting, or background"
    }}
  ],
  "narration": {{
    "exists": true or false,
    "style": "Description of narration style (e.g., documentary, vlog, storytelling)",
    "tone": "Tone of narration (e.g., serious, casual)",
    "emotion": "Emotion of narrator"
  }},
  "analysis_result": {{
    "summary": "1-2 sentence summary of the script",
    "genre": "Script genre (e.g., drama, comedy, education)",
    "overall_mood": "Overall mood of the script"
  }}
}}
"""
        # Call Gemini (using gemini-1.5-flash by default as requested for fast JSON extraction)
        try:
            # We use use_search=False and task_type for standard extraction
            response_text = await self.gemini.generate_text(
                prompt=prompt,
                temperature=0.3,
                task_type="text_gen"
            )
            
            # Extract JSON block if surrounded by markdown
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
            # Fallback mock/error JSON
            return {
                "language": "unknown",
                "characters": [],
                "narration": {
                    "exists": False,
                    "style": "none",
                    "tone": "none",
                    "emotion": "none"
                },
                "analysis_result": {
                    "summary": "Analysis failed",
                    "genre": "unknown",
                    "overall_mood": "unknown"
                },
                "error": str(e)
            }

script_analyzer_service = ScriptAnalyzerService()
