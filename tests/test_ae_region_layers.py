import hashlib
import shutil
import sys
from pathlib import Path
import pytest
from PIL import Image, ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'worker'))
from ae_region_layers import build_layers, load_runtime


def fixture(tmp_path, contour='exact'):
    source=tmp_path/'source.png';im=Image.new('RGB',(320,200),'white');ImageDraw.Draw(im).ellipse((100,40,160,140),fill='red');im.save(source)
    r={'id':'arm','polygon':[[.25,.1],[.6,.1],[.6,.8],[.25,.8]],'contour':contour}
    return source,{'imageSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'geometry':[r]}


def test_uses_reviewed_contour_and_supplied_background(tmp_path):
    source,data=fixture(tmp_path)
    plate=tmp_path/'plate.png';Image.new('RGB',(320,200),'green').save(plate)
    result=build_layers(source,tmp_path/'layers',data,background=plate)
    files={f['role']:f['path'] for f in result['files']}
    layer=Image.open(files['region:arm'])
    assert layer.getpixel((110,70))[3]>240
    assert layer.getpixel((85,25))[3]==0
    assert Image.open(files['background']).getpixel((130,80))==(0,128,0)
    assert Image.open(files['composite']).getpixel((130,80))[0]>200


def test_rejects_automatic_contour_and_background_repair(tmp_path):
    source,data=fixture(tmp_path,'auto')
    plate=tmp_path/'plate.png';Image.new('RGB',(320,200),'green').save(plate)
    with pytest.raises(ValueError,match='자동 외곽선'):build_layers(source,tmp_path/'auto',data,background=plate)
    source,data=fixture(tmp_path,'exact')
    with pytest.raises(ValueError,match='자동 배경'):build_layers(source,tmp_path/'background',data)


def test_occluded_requires_complete_supplement_and_preserves_supplied_plate(tmp_path):
    source,data=fixture(tmp_path);data['geometry'][0]['occluded']=True
    with pytest.raises(ValueError,match='PNG'):build_layers(source,tmp_path/'blocked',data)
    supplement=tmp_path/'hand.png';im=Image.new('RGBA',(320,200));ImageDraw.Draw(im).rectangle((100,10,150,160),fill='blue');im.save(supplement)
    plate=tmp_path/'plate.png';Image.new('RGB',(320,200),'green').save(plate)
    result=build_layers(source,tmp_path/'ready',data,{'arm':supplement},plate)
    assert Image.open(result['files'][0]['path']).getpixel((130,80))==(0,128,0)
    assert Image.open(result['files'][1]['path']).getpixel((120,20))==(0,0,255,255)


def test_reuses_saved_layers_and_rejects_modified_bytes(tmp_path):
    source,data=fixture(tmp_path,'exact');plate=tmp_path/'plate.png';Image.new('RGB',(320,200),'green').save(plate);result=build_layers(source,tmp_path/'layers',data,background=plate)
    for f in result['files']:f['sha256']=hashlib.sha256(f['path'].read_bytes()).hexdigest()
    payload={'layerPackage':{'result':result},'timeline':{'duration':9},'regions':[{'id':'arm','period':4,'anchor':[.3,.3]}]}
    def download(f,p):shutil.copyfile(f['path'],p)
    runtime=load_runtime(tmp_path/'reused',payload,download)
    assert runtime['duration']==9 and runtime['regions'][0]['period']==4
    assert Path(runtime['regions'][0]['path']).read_bytes()==result['files'][1]['path'].read_bytes()
    result['files'][0]['path'].write_bytes(b'changed')
    with pytest.raises(ValueError,match='변경'):load_runtime(tmp_path/'bad',payload,download)
