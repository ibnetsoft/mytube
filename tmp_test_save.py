from database import save_image_prompts

def test_save():
    prompts = [{
        'scene_number': 1,
        'scene_text': 'test',
        'prompt_ko': 'test',
        'prompt_en': 'test'
    }]
    try:
        save_image_prompts(1, prompts)
        print("Success!")
    except Exception as e:
        print("Exception:", e)

if __name__ == '__main__':
    test_save()
