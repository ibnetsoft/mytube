"""Durable, source-bound checkpoints for the supervised registration flow."""
import hashlib
import json
import os
import time

from worker.script_topic_delivery import write


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def acquire_lock(path):
    """Keep the returned stream alive until delivery exits, on Mac/Linux too."""
    stream = path.open('a+b')
    try:
        if path.stat().st_size == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return stream
    except BaseException:
        stream.close()
        raise


def checkpoint_package(path, identity, inputs, build):
    key = fingerprint(inputs)
    if path.exists():
        saved = json.loads(path.read_text(encoding='utf-8-sig'))
        if saved.get('source_job_id') == identity and saved.get('input_sha256') == key:
            package = saved['package']
            if fingerprint(package) != saved.get('package_sha256'):
                raise ValueError('Delivery checkpoint bytes changed')
            return package
    package = build()
    write(path, {'source_job_id': identity, 'input_sha256': key,
                 'package_sha256': fingerprint(package), 'package': package})
    return package


def save_candidate(store, identity, package, root):
    # Persist before the network write: a lost response must never force another
    # expensive generation. Always merge into the latest optimistic revision.
    write(root/'candidate.json', package)
    bundle = store.get(identity)
    if bundle['job'].get('status') == 'canceled':
        raise ValueError('Source job canceled during delivery')
    bundle['candidate'] = package
    bundle['job'].update(status='awaiting_approval', stage='생성 결과 보존 · 웹 등록 준비', updated_at=time.time())
    store.save(bundle)
    return bundle


def complete_registration(store, identity, package, receipt, root):
    bundle = store.get(identity)
    if bundle['job'].get('status') == 'canceled':
        raise ValueError('Source job canceled during delivery')
    if bundle.get('candidate', {}).get('script') != package['script']:
        raise ValueError('Source script changed after registration')
    bundle['candidate'] = package
    bundle['job'].update(published=True, topic_queue_id=receipt['topic_id'],
        published_topic_id=receipt['topic_id'], status='completed',
        stage='대본 생성·유저웹 등록 완료', updated_at=time.time(),
        registration_completed_at=time.time(), delivery_active=False,
        completion_scope='script_package_and_user_web_registration',
        quality_notes_path=str(root/'delivery/quality-notes.json'))
    store.save(bundle)
    verified = store.get(identity)
    if (verified['job'].get('status') != 'completed' or
            verified['job'].get('topic_queue_id') != receipt['topic_id']):
        raise ValueError('Registration completion readback failed')
    write(root/'job.json', verified['job'])
    write(root/'candidate.json', verified['candidate'])
    return verified
