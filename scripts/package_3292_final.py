"""Add a private versioned repair package to the existing project Drive folder."""
import hashlib
import json
import sys
import zipfile
from draft_3292_scoped import OUT, PID, save
sys.path.insert(0,str(OUT.parents[1]/'output/3197_approved_visual_revision/python-deps'))
from services.google_drive_service import GoogleDriveService

def main():
    before=json.loads((OUT/'preapply-source.json').read_text(encoding='utf-8'))
    folder=before['project']['drive_folder_id']
    assert folder=='1NHNFMAnq3yxb39hRryHa7fwcXGWcj6JB'
    service=GoogleDriveService();drive=service._get_drive_service()
    meta=drive.files().get(fileId=folder,fields='id,name,mimeType,trashed').execute()
    assert not meta.get('trashed') and meta['mimeType']=='application/vnd.google-apps.folder'
    package=OUT/'3292-final-79e865def1d9692b-partial49of53.zip'
    if not package.exists():
        with zipfile.ZipFile(package,'w',zipfile.ZIP_STORED) as z:
            for name in ('candidate-final.json','최종-승인대본.md','approved-final-quality.json','character-anchors.json',
                'staged-structure.json','dialogue-annotations.json','publish-metadata.json','subtitles.json',
                'thai-translations.json','uploaded-scene-images.json','thumbnail-upload.json','thumbnail-background.png'):
                z.write(OUT/name,name)
            for p in (OUT/'characters').glob('*.png'):z.write(p,'characters/'+p.name)
            for p in (OUT/'scene-assets/cropped-partial').glob('*.png'):z.write(p,'images/'+p.name)
            plan=json.loads((OUT/'application-plan.json').read_text(encoding='utf-8'))
            z.writestr('project-package.json',json.dumps(plan['project_patch']['project_payload'],ensure_ascii=False,indent=2))
    md5=hashlib.md5(package.read_bytes()).hexdigest()
    found=drive.files().list(q=f"'{folder}' in parents and name = '{package.name}' and trashed = false",fields='files(id,md5Checksum)').execute().get('files',[])
    same=next((x for x in found if x.get('md5Checksum')==md5),None)
    result=same or service.upload_file(str(package),folder_id=folder,filename=package.name,mimetype='application/zip',make_public=False,
        description='Approved 3292 repair: 53 scenes, 49 images. Scenes21-24 missing. Prior versions preserved.')
    assert result and result.get('id')
    actual=drive.files().get(fileId=result['id'],fields='id,name,size,md5Checksum,webViewLink,parents').execute()
    assert actual['md5Checksum']==md5 and int(actual['size'])==package.stat().st_size and folder in actual['parents']
    save('drive-package.json',{**actual,'folder_id':folder,'status':'partial49of53','project_id':PID})
    print('Drive repair package saved and checksum verified.',flush=True)

if __name__=='__main__':main()
