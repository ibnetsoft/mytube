import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'worker'))
from filmcraft_render import PIN, VERSION, CONTRACT
from motion_automation_worker import unseal, NeedsReview, renderer_cache_is_current
from worker.local_media_supervisor import Supervisor, role_command
from worker.workflow_roles import asset_stage, POSTPRODUCTION


def frozen():
    return {'version':1,'renderer':{'engine':'filmcraft','revision':PIN['revision'],'adapter':VERSION,'profile':CONTRACT['profile']},
        'motion':{'production_method':'filmcraft','fps':30,'automation':{'mode':'ae_only'}},
        'scenes':[{'number':1,'start':0,'end':2,'source_kind':'image'}]}


def sealed(value):
    raw=json.dumps(value)
    return {'snapshot_json':raw,'fingerprint':hashlib.sha256(raw.encode()).hexdigest()}


def test_filmcraft_frozen_renderer_cannot_cross_engines_or_revision():
    value=frozen();assert unseal(sealed(value))==value
    for renderer in ({'engine':'effectcraft','revision':PIN['revision']},{'engine':'filmcraft','revision':'0'*40},None):
        bad=copy.deepcopy(value);bad['renderer']=renderer
        with pytest.raises(NeedsReview):unseal(sealed(bad))
    value['scenes'][0]['source_kind']='psd'
    with pytest.raises(NeedsReview):unseal(sealed(value))
    value=frozen();value['renderer']['profile']='old-40mbps'
    with pytest.raises(NeedsReview):unseal(sealed(value))


def test_filmcraft_cache_and_serial_scheduler_are_engine_specific(tmp_path):
    project=tmp_path/'timeline.fcproj';project.write_text('{}')
    receipt=tmp_path/'filmcraft-receipt.json'
    receipt.write_text(json.dumps({'adapter':VERSION,'gpu_composition':{'compositedFrames':1,'adapter':{'deviceType':'DiscreteGpu'}}}))
    from services.video_playback_policy import POLICY
    record={'video_playback_policy':POLICY,'filmcraft_adapter':VERSION,'filmcraft_project':str(project),
        'filmcraft_project_sha256':hashlib.sha256(project.read_bytes()).hexdigest(),
        'filmcraft_receipt':str(receipt),'filmcraft_receipt_sha256':hashlib.sha256(receipt.read_bytes()).hexdigest()}
    assert not renderer_cache_is_current(frozen(),{'effectcraft_compatibility':VERSION})
    assert not renderer_cache_is_current(frozen(),{'filmcraft_adapter':VERSION})
    assert renderer_cache_is_current(frozen(),record)
    project.write_text('{"changed":true}')
    assert not renderer_cache_is_current(frozen(),record)
    assert Supervisor().choose(['filmcraft'])=='filmcraft'
    assert role_command('filmcraft')[-3:]==['--engine','filmcraft','--once']
    assert asset_stage({'metadata':{'kind':'filmcraft_automation'}})==POSTPRODUCTION


def test_web_worker_and_installer_use_identical_source_pin():
    assert PIN==json.loads((ROOT/'tools/filmcraft/source.json').read_text())
