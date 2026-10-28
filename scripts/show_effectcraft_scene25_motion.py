"""Draw an actual-frame difference sheet at the diagnosed worst motion error."""
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
D=Path(__file__).resolve().parents[1]/'output/effectcraft/psd-3376-scene25-motion-fix-20261021'
sheet=Image.new('RGB',(1920,770),'#151515');draw=ImageDraw.Draw(sheet)
images=[np.asarray(Image.open(D/f'{name}-9.png').convert('RGB')).astype(float) for name in ['ae','before','fixed']]
for i,(label,im) in enumerate(zip(['AE | 3.375s','EffectCraft before | 3.375s','EffectCraft fixed | 3.375s'],images)):
    sheet.paste(Image.fromarray(im.astype('uint8')).resize((640,360)),(640*i,25));draw.text((640*i+10,7),label,fill='white')
    delta=np.clip(abs(images[0]-im)*12,0,255).astype('uint8')
    sheet.paste(Image.fromarray(delta).resize((640,360)),(640*i,410));draw.text((640*i+10,392),'Difference from AE x12',fill='white')
sheet.save(D/'motion-before-after.jpg',quality=95)
print('Actual-frame before/after sheet created')
