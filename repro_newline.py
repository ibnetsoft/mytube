import os
import textwrap
from PIL import Image, ImageDraw, ImageFont

def test_newline_wrapping():
    # Mock settings
    width = 1920
    font_size = 80
    font_path = "C:/Windows/Fonts/malgunbd.ttf"
    if not os.path.exists(font_path):
        font_path = "C:/Windows/Fonts/malgun.ttf"
    
    # Text with manual newline
    text = "첫 번째 줄입니다.\n두 번째 줄입니다."
    
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()
        
    safe_width = int(width * 0.9) # 1728
    
    def get_text_width(text, font):
        dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        return dummy_draw.textlength(text, font=font)

    
    # 2. Simulate cleaning
    text = text.replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace('{', '').replace('}', '')
    #Full-width Unicode
    text = text.replace('（', '').replace('）', '').replace('【', '').replace('】').replace('「', '').replace('」').replace('『', '').replace('』')
    text = text.strip()
    
    if not text:
        print("Text became empty after cleaning!")
        return
        
    # 3. Manual Split first
    manual_lines = text.split('\n')
    print(f"Manual Lines: {manual_lines}")
    
    final_wrapped_lines = []
    
    for m_line in manual_lines:
        m_line = m_line.strip()
        if not m_line: continue
        
        line_width = get_text_width(m_line, font)
        print(f"Line '{m_line}' width: {line_width}")
        
        if line_width <= safe_width:
             final_wrapped_lines.append(m_line)
        else:
             print(f"Auto-wrapping long line: {m_line}")
             # Simplified wrapping for repro
             final_wrapped_lines.append(m_line) 

    print(f"Final Lines: {final_wrapped_lines}")

if __name__ == "__main__":
    test_newline_wrapping()
