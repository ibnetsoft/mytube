import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'worker'))
from ae_stage_timing import stage_timing


def test_start_and_end_correlate_and_keep_context(tmp_path):
    path = tmp_path / 'timing.jsonl'
    with stage_timing(path, 'render', scene=59):
        pass
    start, end = [json.loads(line) for line in path.read_text().splitlines()]
    assert start['event'] == 'start' and end['event'] == 'end'
    assert start['event_id'] == end['event_id']
    assert end['scene'] == 59 and end['outcome'] == 'ok'
    assert end['elapsed_seconds'] >= 0


def test_failure_recorded_and_original_exception_preserved(tmp_path):
    path = tmp_path / 'timing.jsonl'
    with pytest.raises(ValueError, match='original'):
        with stage_timing(path, 'render'):
            raise ValueError('original')
    assert json.loads(path.read_text().splitlines()[-1])['outcome'] == 'error'


def test_unwritable_log_does_not_break_job(tmp_path):
    blocker = tmp_path / 'file'
    blocker.write_text('existing')
    with stage_timing(blocker / 'timing.jsonl', 'render'):
        pass
    with pytest.raises(ValueError, match='original'):
        with stage_timing(blocker / 'timing.jsonl', 'render'):
            raise ValueError('original')
