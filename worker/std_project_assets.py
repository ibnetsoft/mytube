"""Read every active project asset despite the PostgREST response row cap."""


def load_project_assets(request, base, headers, project_id, page_size=500, *, or_filter=None):
    assets = []
    offset = 0
    while True:
        page = request('GET', base + '/rest/v1/std_project_assets', headers, params={
            'select': '*', 'project_id': 'eq.' + project_id,
            'status': 'in.(uploaded,assigned)', 'order': 'created_at.desc,id.desc',
            'limit': str(page_size), 'offset': str(offset),
            **({'or': or_filter} if or_filter else {}),
        }).json()
        if not isinstance(page, list):
            raise ValueError('Project asset query did not return a list')
        assets.extend(page)
        if len(page) < page_size:
            return assets
        offset += len(page)


def load_project_input_assets(request, base, headers, project_id, page_size=500):
    """Read all frozen-input candidates, excluding unrelated job/cache history.

    Keep complete metadata and pagination: new original media and changed
    references must still invalidate an in-flight review.
    """
    return load_project_assets(request, base, headers, project_id, page_size,
        or_filter='(asset_type.in.(audio,image,video),metadata->>kind.in.(speaker_video_reference,eye_blink_confirmation))')
