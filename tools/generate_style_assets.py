import sys
import os
import asyncio

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from services.gemini_service import gemini_service

async def main():
    styles = {
        "realistic": "A highly realistic photo of a modern workspace with a laptop and coffee, sunlit, 8k resolution, highly detailed photography, standard view",
        "anime": "Anime style illustration of a magical library with glowing books, vibrant colors, detailed background, Makoto Shinkai style",
        "cinematic": "Cinematic movie shot of a cyber city at night, rain, neon lights, dramatic lighting, shallow depth of field, anamorphic lens",
        "minimal": "Minimalist flat vector illustration of a workspace, simple shapes, pastel color palette, clean lines, white background",
        "3d": "3D render of a cute robot mascot sitting on a desk, Pixar style, soft studio lighting, octane render, 4k",
        "webtoon": "Oriental fantasy webtoon style illustration of a character in traditional clothing lying on a bed in a dark room, dramatic lighting, detailed line art, manhwa aesthetics, high quality"
    }
    
    output_dir = os.path.join(project_root, "static", "img", "styles")
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Output directory: {output_dir}")
    
    for name, prompt in styles.items():
        print(f"Generating {name}...")
        try:
            # aspect_ratio needs to be supported by the service. 
            # Looking at gemini_service.py, it maps 16:9 etc.
            # I'll use 1:1 for thumbnails.
            images = await gemini_service.generate_image(prompt, aspect_ratio="1:1")
            if images:
                file_path = os.path.join(output_dir, f"style_{name}.png")
                with open(file_path, "wb") as f:
                    f.write(images[0])
                print(f"Saved style_{name}.png")
            else:
                print(f"Failed to generate {name} (No detailed error, check service logs)")
        except Exception as e:
            print(f"Error generating {name}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
