import math
import re

import pytest

from worker.paragraph_scene_pacing import MODE, opening_schedule, paragraph_scenes


def test_short_paragraphs_and_short_tail_merge_without_losing_prose():
    paragraphs = ['あ' * 40, 'い' * 50, 'う' * 100, 'え' * 10]
    scenes = paragraph_scenes(paragraphs, 50, 4)
    assert [s['text'] for s in scenes] == [paragraphs[0] + '\n\n' + paragraphs[1], paragraphs[2] + '\n\n' + paragraphs[3]]
    assert sum(s['duration_seconds'] for s in scenes) == 50
    assert all(s['duration_seconds'] >= 18 for s in scenes)
    assert '\n\n'.join(s['text'] for s in scenes) == '\n\n'.join(paragraphs)


def test_long_paragraph_is_never_split_into_18_second_images():
    paragraphs = ['あ' * 240, 'い' * 120]
    scenes = paragraph_scenes(paragraphs, 90, 4)
    assert [s['duration_seconds'] for s in scenes] == [60, 30]
    assert [s['text'] for s in scenes] == paragraphs


def test_over_three_minutes_splits_at_japanese_sentence_boundaries():
    paragraph = ('あ' * 99 + '。') * 20
    scenes = paragraph_scenes([paragraph], 500, 4)
    assert len(scenes) >= 3
    assert all(18 <= s['duration_seconds'] <= 180 for s in scenes)
    assert all(s['text'].endswith('。') for s in scenes)
    assert ''.join(s['text'] for s in scenes) == paragraph
    assert sum(s['duration_seconds'] for s in scenes) == 500


def test_short_tail_rebalances_instead_of_extending_past_three_minutes():
    first = ('あ' * 79 + '。') * 9  # Exactly 180s, followed by a short 10s paragraph.
    last = 'い' * 39 + '。'
    scenes = paragraph_scenes([first, last], 190, 4)
    assert len(scenes) == 2
    assert all(18 <= s['duration_seconds'] <= 180 for s in scenes)
    assert re.sub(r'\s', '', ''.join(s['text'] for s in scenes)) == first + last
    assert sum(s['duration_seconds'] for s in scenes) == 190


def test_exact_three_minutes_is_allowed_but_an_indivisible_overlong_sentence_fails():
    assert paragraph_scenes(['あ' * 720], 180, 4)[0]['duration_seconds'] == 180
    with pytest.raises(ValueError, match='sentence boundaries'):
        paragraph_scenes(['あ' * 721], 181, 4)


def test_english_sentence_split_retains_closing_quotes_and_all_words():
    paragraph = ('The door opened. ' * 60 + '"Who is there?" ') * 4
    seconds = round(len(re.sub(r'\s', '', paragraph)) / 4)
    scenes = paragraph_scenes([paragraph], seconds, 4)
    assert all(18 <= s['duration_seconds'] <= 180 for s in scenes)
    assert re.sub(r'\s', '', ''.join(s['text'] for s in scenes)) == re.sub(r'\s', '', paragraph)


def test_whitespace_does_not_count_as_spoken_narration():
    with pytest.raises(ValueError, match='too short'):
        paragraph_scenes(['あ' * 10 + ' ' * 1000], 900, 4)


def test_minimum_survives_duration_rounding_and_last_remainder():
    scenes = paragraph_scenes(['あ' * 72, 'い' * 72, 'う' * 76], 55, 4)
    assert [s['duration_seconds'] for s in scenes] == [18, 18, 19]
    assert paragraph_scenes(['あ' * 80, 'い' * 10], 20, 4)[0]['duration_seconds'] == 20


def test_fixed_opening_runs_once_then_later_chapters_have_only_paragraphs():
    opening = opening_schedule(900)
    assert len(opening) == 60
    assert sum(s['duration_seconds'] for s in opening) == 597
    assert opening_schedule(900, 900) == []


@pytest.mark.parametrize('elapsed,expected_head,expected_seconds', [(0, 60, 303), (900, 0, 900)])
def test_runner_uses_prose_before_planning_and_keeps_variable_scene_count(elapsed, expected_head, expected_seconds):
    from worker.codex_content_runner import CodexStagedContentRunner

    class PlanReached(Exception):
        pass

    class Runner(CodexStagedContentRunner):
        def _stage(self, job_id, stage, context, task):
            if stage == '02p_paragraph_narration':
                assert len(context['opening_schedule']) == expected_head
                assert context['body_target_seconds'] == expected_seconds
                # Two natural long paragraphs, deliberately not 18-second units.
                chars = context['body_target_chars']
                def prose(char, count):
                    return (char * 39 + '。') * (count // 40) + char * (count % 40)
                return {'opening_sections': ['冒頭です。' * 5] * expected_head,
                        'paragraphs': [prose('あ', chars // 2), prose('い', chars - chars // 2)]}
            assert stage == '01_plan'
            assert len(context['paragraph_sections']) >= expected_head + math.ceil(expected_seconds / 180)
            if not elapsed:
                assert len(context['paragraph_sections']) == expected_head + 2
            assert context['scene_boundary_policy'] == MODE
            assert context['paragraph_scene_start'] == expected_head + 1
            assert 'Never split, merge' in task
            assert ('without a new opening' in task) == bool(elapsed)
            raise PlanReached

    with pytest.raises(PlanReached):
        Runner().generate('paragraph-test', {'language': 'ja', 'script_style': 'story', 'category_id': 13,
            'target_duration_seconds': 900, '_scene_boundary_mode': MODE, '_story_elapsed_seconds': elapsed})
