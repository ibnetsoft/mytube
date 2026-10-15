import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from mouth_geometry import validate, animatable, fingerprint

def speaker():
    return {'speaker':'elder','status':'visible','face_box':[.2,.1,.6,.7], 'mouth_box':[.35,.44,.45,.5],
        'mouth_geometry':{'version':2,'source_sha256':'a'*64,'orientation':'frontal','pitch':'level',
        'mouth_visibility':'clear','render_policy':'animate','evidence':'visible lip contour',
        'face_outline':[[.2,.1],[.6,.1],[.6,.6],[.4,.7],[.2,.6]],
        'landmarks':{'nose_tip':[.4,.35],'chin':[.4,.65],'lip_left':[.36,.47],
                     'lip_right':[.44,.47],'lip_center':[.4,.47]},
        'review':{'passed':True,'reason':'original crop verified','proof':'annotated-face-crop-v4'}}}

def test_clear_front_profile_and_downward_have_explicit_geometry():
    for pose,pitch in [('frontal','level'),('profile_left','level'),('three_quarter_right','down')]:
        s=speaker();s['mouth_geometry'].update(orientation=pose,pitch=pitch)
        assert animatable(s,'a'*64)

def test_cheek_mouth_inside_face_box_is_rejected():
    s=speaker();s['mouth_box']=[.51,.44,.59,.5]
    s['mouth_geometry']['landmarks'].update(lip_left=[.52,.47],lip_right=[.58,.47],lip_center=[.55,.47])
    with pytest.raises(ValueError,match='cheek'):validate(s)

def test_lips_outside_real_face_silhouette_are_rejected():
    s=speaker();s['mouth_geometry']['face_outline']=[[.2,.1],[.6,.1],[.6,.3],[.3,.4],[.2,.3]]
    with pytest.raises(ValueError,match='contour'):validate(s)

def test_hidden_mouth_never_animates_or_requires_guessed_lips():
    s=speaker();s.update(status='occluded',mouth_box=None)
    s['mouth_geometry'].update(mouth_visibility='hidden',render_policy='preserve_original',landmarks={})
    assert not animatable(s)
    validate(s)
    s['mouth_geometry']['render_policy']='animate'
    with pytest.raises(ValueError,match='preserve'):validate(s)

def test_old_box_and_unreviewed_new_geometry_are_not_ready():
    s=speaker();s.pop('mouth_geometry')
    with pytest.raises(ValueError,match='legacy'):validate(s)
    s=speaker();s['mouth_geometry']['review']['passed']=False
    with pytest.raises(ValueError,match='independent'):validate(s)

def test_source_change_and_pose_change_invalidate_cache():
    s=speaker()
    with pytest.raises(ValueError,match='different source'):validate(s,'b'*64)
    other=copy.deepcopy(s);other['mouth_geometry']['orientation']='profile_right'
    assert fingerprint(s)!=fingerprint(other)

def test_unreviewed_technical_patch_cache_is_never_reused(tmp_path,monkeypatch):
    import prepared_mouth_layers as prepared
    from PIL import Image
    image=tmp_path/'image.png';Image.new('RGB',(100,100)).save(image)
    s=speaker();s['mouth_geometry']['source_sha256']=__import__('hashlib').sha256(image.read_bytes()).hexdigest()
    monkeypatch.setattr(prepared,'ROOT',tmp_path/'cache')
    directory=prepared.ROOT/prepared.cache_key(image,s);directory.mkdir(parents=True)
    (directory/'artifact-ready.json').write_text('{}')
    assert prepared.reuse_prepared(image,s) is False

def test_blank_cheek_pixels_cannot_pass_coordinate_review():
    from PIL import Image,ImageDraw
    from mouth_geometry import validate_image_evidence
    image=Image.new('RGB',(1000,1000),'#dbc0a5')
    s=speaker()
    with pytest.raises(ValueError,match='lip-line pixels'):validate_image_evidence(s,image)
    ImageDraw.Draw(image).line((360,470,440,470),fill='black',width=3)
    validate_image_evidence(s,image)
