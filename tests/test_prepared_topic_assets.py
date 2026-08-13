from app.routers import user_topics


def test_prepared_structure_accepts_worker_fallback_media_fields():
    structure = {
        "media_prompt_status": "fallback_ready",
        "scenes": [
            {
                "scene_order": 1,
                "scene_title": "Opening",
                "visual_description": "A newsroom screen shows anxious workers.",
                "motion_desc": "Slow push-in on the worried presenter.",
                "media_prompt_status": "fallback_ready",
            }
        ],
    }

    assert user_topics._structure_has_ready_media_prompts(structure) is True


def test_recommendable_topic_requires_ready_media_prompts():
    topic = {
        "status": "pending",
        "generated_title": "월급 300인데 집값 10억",
        "category_id": "cat-1",
        "pregenerated_structure_status": "ready",
        "pregenerated_structure": {
            "media_prompt_status": "missing",
            "scenes": [
                {
                    "scene_order": 1,
                    "scene_title": "Opening",
                    "scene_summary": "Housing anxiety opens the story.",
                    "media_prompt_status": "missing",
                }
            ],
        },
        "pregenerated_script_status": "ready",
        "pregenerated_script": "Ready narration.",
    }

    assert user_topics._is_recommendable_topic(topic) is False


def test_pregenerated_structure_copies_image_and_video_prompts():
    structure = {
        "media_prompt_status": "ready",
        "scenes": [
            {
                "scene_order": 3,
                "scene_title": "Job Shock",
                "scene_summary": "AI changes the office routine.",
                "image_prompt": "Detailed image prompt",
                "video_prompt": "Detailed video prompt",
                "media_prompt_status": "ready",
            }
        ],
    }

    prompts = user_topics._image_prompts_from_pregenerated_structure(structure)

    assert prompts == [
        {
            "scene_number": 3,
            "scene_title": "Job Shock",
            "scene_text": "AI changes the office routine.",
            "prompt_ko": "AI changes the office routine.",
            "prompt_en": "Detailed image prompt",
            "motion_desc": "Detailed video prompt",
            "flow_prompt": "Detailed video prompt",
            "visual_style": "",
            "lighting_hint": "",
            "shot_hints": [],
        }
    ]
