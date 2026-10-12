"""Read full project asset bundles without the PostgREST response cap."""
def read_project_assets(request, url, headers, project_id, asset_types=None):
    rows = []
    offset = 0
    while True:
        params = {
            'select': '*', 'project_id': 'eq.' + project_id,
            'order': 'created_at.desc,id.desc', 'offset': offset, 'limit': 1000,
        }
        if asset_types:
            params['asset_type'] = 'in.(' + ','.join(asset_types) + ')'
        page = request('GET', url, headers, params=params).json()
        rows.extend(page)
        if len(page) < 1000:
            return rows
        offset += 1000
