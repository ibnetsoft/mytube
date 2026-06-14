import asyncio
import os
import sys

# 프로젝트 루트 경로 추가
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.gemini_service import gemini_service
import config

async def test():
    prompt = "Create a strict 2x2 grid layout (exactly 2 columns and 2 rows, 4 equal-sized panels total). Do NOT add any extra panels, text, or borders. Each panel must represent one scene:\n- Panel 1 (Position: Top-Left): A doctor talking to a patient.\n- Panel 2 (Position: Top-Right): A woman pointing at a chart.\n- Panel 3 (Position: Bottom-Left): A woman eating salad.\n- Panel 4 (Position: Bottom-Right): A woman holding a meter.\nCRITICAL: You must generate EXACTLY 4 panels in a perfect 2x2 grid. No more, no less. Maintain consistent characters across all panels."
    
    print("Generating image...")
    images_bytes = await gemini_service.generate_image(
        prompt=prompt,
        num_images=1,
        aspect_ratio="1:1"
    )
    
    if images_bytes:
        with open("test_grid_output.png", "wb") as f:
            f.write(images_bytes[0])
        print("Saved to test_grid_output.png")
    else:
        print("Failed to generate image")

if __name__ == "__main__":
    asyncio.run(test())
