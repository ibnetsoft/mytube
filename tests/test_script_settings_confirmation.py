from unittest.mock import patch
import pytest
from fastapi import HTTPException
from worker import codex_local_console as console

def test_new_script_requires_settings_confirmation_before_queueing():
 with patch.object(console.jobs,'start') as start:
  with pytest.raises(HTTPException) as error:console.start(console.StartRequest(mode='new',title='test',category='story'))
  assert error.value.status_code==409
  start.assert_not_called()

def test_confirmed_settings_reach_worker_unchanged():
 request=console.StartRequest(mode='new',settings_confirmed=True,title='test',category='story',duration_minutes=60,language='ja',image_layer_mode='full_psd')
 with patch.object(console,'load_script_settings',return_value={'duration_minutes':15,'language':'ko'}),patch.object(console.jobs,'start',return_value={'id':'test'}) as start:
  assert console.start(request)=={'id':'test'}
  actual=start.call_args.args[0];assert actual.duration_minutes==60;assert actual.language=='ja';assert actual.image_layer_mode=='full_psd';assert actual.settings_confirmed
