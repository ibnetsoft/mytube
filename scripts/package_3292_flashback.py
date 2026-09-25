"""Preserve old private package and add a verified52-image repair package."""
import hashlib,json,sys,zipfile
from datetime import datetime,timezone
import requests
from flashback_3292 import DEST,OUT,PID,UID,read,write,capture
from scripts.repair_existing_topic_scripts import _headers
sys.path.insert(0,str(OUT.parents[1]/'output/3197_approved_visual_revision/python-deps'))
from services.google_drive_service import GoogleDriveService

def main():
    before=capture();p=before['project'];folder=p['drive_folder_id']
    assert folder=='1NHNFMAnq3yxb39hRryHa7fwcXGWcj6JB'
    assert p['progress_payload']['image_recovery_revision']['image_count']==52
    service=GoogleDriveService();drive=service._get_drive_service()
    meta=drive.files().get(fileId=folder,fields='id,name,mimeType,trashed').execute()
    assert not meta.get('trashed') and meta['mimeType']=='application/vnd.google-apps.folder'
    package=DEST/'3292-flashback-v2-partial52of53.zip'
    old=OUT/'3292-final-79e865def1d9692b-partial49of53.zip'
    combined=read(OUT/'uploaded-scene-images.json');combined['assets']+=read(DEST/'uploaded-assets.json')['assets'];combined.update(status='partial',missing_scene_numbers=[24])
    assert len(combined['assets'])==52
    replacements={'project-package.json':p['project_payload'],'staged-structure.json':p['project_payload']['structure'],
       'subtitles.json':p['project_payload']['subtitles'],'uploaded-scene-images.json':combined,
       'flashback-character-anchors.json':read(DEST/'flashback-character-anchors.json'),
       'flashback-prompts.json':read(DEST/'manifest.json'),'db-verification.json':read(DEST/'db-verification.json')}
    if not package.exists():
        with zipfile.ZipFile(old) as source,zipfile.ZipFile(package,'w',zipfile.ZIP_STORED) as z:
            for name in source.namelist():
                if name not in replacements:z.writestr(name,source.read(name))
            for name,value in replacements.items():z.writestr(name,json.dumps(value,ensure_ascii=False,indent=2))
            for path in (DEST/'cropped').glob('scene-*.png'):z.write(path,'images/'+path.name)
            for name in ('geumrye38','sunduk12'):z.write(DEST/(name+'.png'),'characters/flashback-'+name+'.png')
    with zipfile.ZipFile(package) as z:
        assert len([n for n in z.namelist() if n.startswith('images/') and n.endswith('.png')])==52
        assert len(z.namelist())==len(set(z.namelist()))
        assert 'images/scene-024.png' not in z.namelist()
    md5=hashlib.md5(package.read_bytes()).hexdigest()
    found=drive.files().list(q=f"'{folder}' in parents and name = '{package.name}' and trashed = false",fields='files(id,md5Checksum)').execute().get('files',[])
    result=next((x for x in found if x.get('md5Checksum')==md5),None) or service.upload_file(str(package),folder_id=folder,filename=package.name,mimetype='application/zip',make_public=False,
       description='3292 flashback revision:52 of53 scene images. Only scene24 missing. Two age-specific character references. Earlier versions preserved.')
    assert result and result.get('id')
    actual=drive.files().get(fileId=result['id'],fields='id,name,size,md5Checksum,webViewLink,parents').execute()
    assert actual['md5Checksum']==md5 and int(actual['size'])==package.stat().st_size and folder in actual['parents']
    record={**actual,'folder_id':folder,'status':'partial52of53','project_id':PID}
    write(DEST/'drive-package.json',record)
    current=capture()['project'];assert current['progress_payload']['image_recovery_revision']['image_count']==52
    write(DEST/'before-package-link.json',current)
    progress={**current['progress_payload'],'visual_package_drive':record}
    base,headers=_headers();r=requests.patch(base+'/rest/v1/std_projects',params={'id':'eq.'+PID,'user_id':'eq.'+UID,
       'updated_at':'eq.'+current['updated_at'],'submitted_at':'is.null','status':'in.(claimed,in_progress)'},headers={**headers,'Prefer':'return=representation'},
       json={'progress_payload':progress,'updated_at':datetime.now(timezone.utc).isoformat()},timeout=90)
    r.raise_for_status();assert len(r.json())==1
    verify=capture()['project'];assert verify['progress_payload']['visual_package_drive']==record
    assert verify['project_payload']==current['project_payload']
    print('Private52-image package saved and checksum verified; project pointer updated.')

if __name__=='__main__':main()
