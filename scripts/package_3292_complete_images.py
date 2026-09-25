"""Create current private backup; leave prior backups untouched."""
import hashlib,json,sys,zipfile
from datetime import datetime,timezone
from check_3292_current import capture
from draft_3292_scoped import OUT,save

def main():
    snapshot=capture();p=snapshot['project'];v=p['project_payload']
    target=OUT/'3292-reviewed-53-images-thai.zip'
    assert not target.exists(),'Preserve existing archive'
    old=OUT/'3292-final-79e865def1d9692b-partial49of53.zip'
    flash=OUT/'scene-assets/flashback-v2'
    replacement={'project-package.json':v,'staged-structure.json':v['structure'],'subtitles.json':v['subtitles'],
      'thai-reviewed.json':json.loads((OUT/'thai-reviewed.json').read_text(encoding='utf-8')),
      'current-snapshot.json':snapshot,'current-image-verification.json':json.loads((flash/'scene24-db-verification.json').read_text(encoding='utf-8'))}
    with zipfile.ZipFile(old) as source,zipfile.ZipFile(target,'w',zipfile.ZIP_STORED) as z:
        for name in source.namelist():
            if name not in replacement:z.writestr(name,source.read(name))
        for name,value in replacement.items():z.writestr(name,json.dumps(value,ensure_ascii=False,indent=2))
        for path in (flash/'cropped').glob('scene-*.png'):z.write(path,'images/'+path.name)
        for name in ['geumrye38','sunduk12']:z.write(flash/(name+'.png'),'characters/flashback-'+name+'.png')
        z.writestr('CURRENT-STATUS.txt','Current source:current-snapshot.json.53 scene images; reviewed Thai263 blocks. Older records retained as history. Audio and final thumbnail are not marked complete.')
    with zipfile.ZipFile(target) as z:
        assert len(z.namelist())==len(set(z.namelist()))
        assert sum(n.startswith('images/') and n.endswith('.png') for n in z.namelist())==53
        assert z.testzip() is None
    report={'local_path':str(target),'image_count':53,'thai_blocks':263,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'drive_status':'pending'}
    save('remaining-backup.json',report)
    sys.path.insert(0,str(OUT.parents[1]/'output/3197_approved_visual_revision/python-deps'))
    from services.google_drive_service import GoogleDriveService
    try:
        service=GoogleDriveService();drive=service._get_drive_service()
        folder=p['drive_folder_id'];meta=drive.files().get(fileId=folder,fields='id,mimeType,trashed').execute()
        assert not meta.get('trashed') and meta['mimeType']=='application/vnd.google-apps.folder'
        result=service.upload_file(str(target),folder_id=folder,filename=target.name,mimetype='application/zip',make_public=False)
        assert result and result.get('id')
        actual=drive.files().get(fileId=result['id'],fields='id,size,md5Checksum,parents').execute()
        assert actual['md5Checksum']==hashlib.md5(target.read_bytes()).hexdigest() and folder in actual['parents']
        report.update(drive_status='verified',drive_file=actual)
    except Exception as e:
        report.update(drive_status='blocked',error_type=type(e).__name__,error=str(e)[:200])
    save('remaining-backup.json',report);print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
