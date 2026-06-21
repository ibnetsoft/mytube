import sys

html_file = r"c:\Users\kimse\Downloads\YoutubeSourceFinder\LongformGenerator\templates\pages\settings.html"
with open(html_file, "r", encoding="utf-8") as f:
    content = f.read()

# Remove the incorrectly placed tab button
bad_btn = """            <button onclick="switchTab('history')" id="tab-history" class="tab-button">
                수당 내역 (History)
            </button>
"""
if bad_btn in content:
    content = content.replace(bad_btn, "")

# Insert it before the if statement
correct_btn = """            <button onclick="switchTab('history')" id="tab-history" class="tab-button">
                수당 내역 (History)
            </button>
            {% if not is_standard_member %}"""
if "{% if not is_standard_member %}" in content:
    # Only replace the FIRST occurrence to insert the tab button
    content = content.replace("{% if not is_standard_member %}", correct_btn, 1)

with open(html_file, "w", encoding="utf-8") as f:
    f.write(content)
print("Fixed tab visibility in settings.html")
