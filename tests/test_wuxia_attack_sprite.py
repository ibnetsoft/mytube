import copy,sys
from pathlib import Path
import pytest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from wuxia_attack_sprite import validate,validate_alpha,CONTRACT

def loop():
 return {'source_sha256':'a'*64,'start_ms':833,'end_ms':1333,'repeat':False,'attack_sprite':{'contract':CONTRACT,'source_sha256':'a'*64,'source_reviewed':True,'frames_reviewed':True,'event':'blade contact','reason':'reviewed electrical skill','contact_ms':750,'protected_boxes':[[.1,.1,.3,.3]]}}

def test_true_transparent_protection_checks_pixels_not_only_the_manifest():
 data=loop();alpha=Image.new('L',(100,100),0);alpha.putpixel((70,80),255);validate_alpha(data,alpha)
 alpha.putpixel((15,15),1)
 with pytest.raises(ValueError,match='protected artwork'):validate_alpha(data,alpha)

@pytest.mark.parametrize('field,value',[('source_sha256','b'*64),('contact_ms',900),('frames_reviewed',False),('protected_boxes',[[0,0,2,2]])])
def test_changed_source_or_unreviewed_and_late_contact_fail(field,value):
 data=loop();data['attack_sprite'][field]=value
 with pytest.raises(ValueError):validate(data)

def test_electrical_sprite_cannot_turn_into_an_ambient_whole_scene_loop():
 for patch in [{'repeat':True},{'end_ms':2000}]:
  with pytest.raises(ValueError):validate({**loop(),**patch})
