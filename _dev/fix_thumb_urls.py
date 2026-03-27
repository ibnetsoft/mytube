import database as db
conn = db.get_db()
cursor = conn.cursor()
cursor.execute('SELECT style_key, image_url FROM thumbnail_style_presets')
rows = cursor.fetchall()
for row in rows:
    sk = row['style_key']
    iu = row['image_url']
    if iu and not iu.startswith('/'):
        new_url = '/' + iu
        cursor.execute('UPDATE thumbnail_style_presets SET image_url = ? WHERE style_key = ?', (new_url, sk))
        print(f"Updated {sk}: {new_url}")
conn.commit()
conn.close()
print("Done.")
