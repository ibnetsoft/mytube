import jinja2
import os

templates = jinja2.Environment(loader=jinja2.FileSystemLoader('templates'))

try:
    template = templates.get_template('pages/webtoon_studio.html')
    # Mocking what FastAPI passes
    output = template.render(request={'url_for': lambda x: x}, title="Webtoon Studio", page="webtoon-studio")
    print("Template rendered successfully!")
except Exception as e:
    print(f"Template rendering failed: {e}")
    import traceback
    traceback.print_exc()
