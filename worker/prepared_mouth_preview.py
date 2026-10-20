"""Keep prepared mouth art before submission; AE execution belongs to postproduction."""
def prepare_preview(topic_id, number, image, geometry, preparation):
    # Older callers use this hook while publishing images. Preserve their receipt
    # shape without starting AE, generating a clip, or enqueueing a render.
    return {'state':'prepared' if preparation.get('state')=='ready' else 'not_required',
            'kind':'mouth_preparation','voice_synced':False,'scene_number':number,
            'prepared_keys':preparation.get('keys',[]),'execution_owner':'postproduction'}
