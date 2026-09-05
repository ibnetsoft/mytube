import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

GUARDED_FUNCTIONS = {
    "worker/hermes_worker.py": {
        "_fallback_publish_metadata",
        "_fallback_music_prompt_tasks",
        "_fallback_visual_direction_plan",
        "_build_fallback_scene_plan",
        "_fallback_narration_section",
        "_fallback_main_character",
        "_fallback_narrative_blueprint",
        "_fallback_script_quality_report",
        "_script_rescue_scene_text",
        "_build_korean_language_rescue_script",
        "_build_japanese_language_rescue_script",
    },
    "worker/hermes_autopilot.py": {"_category_fallback_title"},
    "services/autopilot_service.py": {"_generate_fallback_image"},
    "services/video_builder_service.py": {"_fallback_director_plan"},
}


def _first_executable_statement(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.stmt | None:
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return body[0] if body else None


def test_synthetic_content_fallback_functions_are_hard_disabled():
    for relative_path, function_names in GUARDED_FUNCTIONS.items():
        tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for function_name in function_names:
            assert function_name in functions
            assert isinstance(_first_executable_statement(functions[function_name]), ast.Raise), (
                f"{relative_path}:{function_name} must fail instead of generating substitute content"
            )


def test_active_generation_paths_do_not_report_fallback_completion():
    sources = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in GUARDED_FUNCTIONS
    )
    forbidden = (
        "Both models failed to generate script. Using fallback draft script.",
        "Music prompt AI generation failed; using fallback prompts",
        "Image style selection failed; using category default",
        "Generating default analysis",
        "default_fallback_vid",
    )
    for marker in forbidden:
        assert marker not in sources
