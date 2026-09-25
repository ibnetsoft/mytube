"""Read back localization, imagery and finalized thumbnail without status inflation."""
import hashlib,json
from check_3292_current import capture
from draft_3292_scoped import OUT,save

data=capture();p=data['project'];v=p['project_payload'];q=data['topic'][0]
save('remaining-final-snapshot.json',data)
assert len(v['structure']['scenes'])==53
assert all(s.get('image_url') for s in v['structure']['scenes'])
assert len(v['subtitles'])==len(v['subtitle_translations']['th']['blocks'])==263
for i,(s,t) in enumerate(zip(v['subtitles'],v['subtitle_translations']['th']['blocks'])):
    assert t['index']==i and t['source_text'].strip()==s['text'].strip() and t['translated_text'].strip()
assert v['subtitle_translations']['th']['source_script_sha256']==hashlib.sha256(v['script'].encode()).hexdigest()
assert p['progress_payload']['thumbnail_completed'] and v['thumbnail_url'] and v['thumbnail_design']['saved_at']
assert v['thumbnail_design']['render_status']=='completed'
report={'topic':3292,'thai_blocks_verified':263,'scene_images_verified':53,'thai_title_saved':bool(q['topic_th']),
 'thai_metadata_saved':bool(v['publish_metadata_translations']['th']), 'thumbnail_final_saved':True,
 'thumbnail_note':'Final-save marker verified in progress_payload and thumbnail_design; legacy top-level flags are stale',
 'voice_language':'ko','tts_completed':bool(p['progress_payload'].get('tts_completed')),
 'audio_blocker':'Web requires a separate dialogue voice; awaiting user selection; no local ElevenLabs key',
 'drive_backup':'blocked by desktop-drive-token bridge_error','local_backup':'3292-reviewed-53-images-thai.zip'}
save('remaining-verification.json',report);print(json.dumps(report,ensure_ascii=False))
