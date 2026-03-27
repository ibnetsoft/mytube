with open("database.py", "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if "def get_image_prompts" in line or "def save_image_prompts" in line:
            print(f"{i+1}: {line.strip()}")
