"""Bounded recovery for malformed generated data, without hiding failed reviews."""
import copy
import re

PROFILE = 'generation_validation/v1'


def validated_stage(stage, name, context, task, validate, attempts=3):
    if type(attempts) is not int or attempts < 1:
        raise ValueError('Validation recovery requires at least one bounded attempt')
    feedback = None
    for attempt in range(attempts):
        supplied = copy.deepcopy(context)
        if feedback is not None:
            supplied['validation_retry'] = {'attempt': attempt + 1, **copy.deepcopy(feedback)}
        retry_task = task if feedback is None else task + '\nThe previous response failed data validation. Use validation_retry.error to repair only invalid fields or scenes, preserving valid narration and facts. Return the complete required JSON. Do not invent evidence or turn a failed review into a pass.'
        result = stage(name, supplied, retry_task)
        try:
            if not isinstance(result, dict):
                raise ValueError('Generated response must be a JSON object')
            validate(result)
            return result
        except (ValueError, AssertionError, KeyError, TypeError) as exc:
            # Including the rejected data and attempt gives _stage a new cache
            # fingerprint. Never edit an old response or retry a transport error.
            feedback = {'error': str(exc), 'rejected_response': result}
    raise ValueError(f'{name} validation failed after {attempts} attempts: {feedback["error"]}')


def validate_sections(result, budgets):
    sections = result.get('sections') if isinstance(result, dict) else None
    if not isinstance(sections, list) or len(sections) != len(budgets):
        raise ValueError(f'Expected exactly {len(budgets)} ordered sections')
    for number, (section, budget) in enumerate(zip(sections, budgets), 1):
        if not isinstance(section, dict) or type(section.get('scene_order')) is not int or section['scene_order'] != number:
            raise ValueError(f'Section {number} has an invalid scene_order')
        text = section.get('text')
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f'Section {number} narration is empty or not text')
        low, high = budget['min_chars'], max(budget['max_chars'] * 2, budget['max_chars'] + 30)
        if not low <= len(text.strip()) <= high:
            raise ValueError(f'Section {number} requires {low}..{high} characters; got {len(text.strip())}. Repair this scene without padding or changing facts.')


def grounded_quote(quote, source):
    """Accept separated verbatim paragraphs, never blank or fabricated evidence."""
    if not isinstance(quote, str) or not quote.strip():
        return False
    parts = [part.strip() for part in re.split(r'\n\s*\n', quote.replace('\r\n', '\n')) if part.strip()]
    source = source.replace('\r\n', '\n')
    cursor = 0
    for part in parts:
        found = source.find(part, cursor)
        if found < 0:
            return False
        cursor = found + len(part)
    return bool(parts)


def validate_story_review(review, script, required_checks):
    if not isinstance(review, dict) or review.get('verdict') not in ('pass', 'repair'):
        raise ValueError('Story review missing verdict')
    checks = review.get('checks')
    if not isinstance(checks, dict) or set(checks) != set(required_checks):
        raise ValueError('Story review must contain every named check')
    for name, check in checks.items():
        if not isinstance(check, dict) or type(check.get('passed')) is not bool or not grounded_quote(check.get('evidence_quote'), script):
            raise ValueError(f'Story review {name} lacks a boolean verdict or grounded evidence')
    issues = review.get('critical_issues')
    notes = review.get('quality_notes')
    if not isinstance(issues, list) or not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
        raise ValueError('Story review findings must be lists')
    if review['verdict'] == 'pass' and (issues or any(not check['passed'] for check in checks.values())):
        raise ValueError('Story review pass contradicts its findings')


def validate_registration_update(topic):
    if topic.get('status') != 'pending' or topic.get('assigned_employee_email'):
        raise ValueError('Do not replace a claimed topic')
    progress = topic.get('progress_payload') or {}
    scenes = (topic.get('pregenerated_structure') or {}).get('scenes') or []
    if progress.get('scene_assets_ready') or progress.get('scene_image_count') or any(
        scene.get('image_url') or scene.get('video_url') or scene.get('layer_assets') for scene in scenes
    ):
        raise ValueError('Do not replace delivered scene assets with prompt-only data')


def validate_registration_readback(saved, expected):
    for key in ('pregenerated_script', 'pregenerated_structure', 'language', 'status'):
        if saved.get(key) != expected[key]:
            raise ValueError(f'Registration readback mismatch: {key}')
    for key in ('local_script_job_id', 'script_sha256'):
        if (saved.get('progress_payload') or {}).get(key) != expected['progress_payload'][key]:
            raise ValueError(f'Registration marker mismatch: {key}')
