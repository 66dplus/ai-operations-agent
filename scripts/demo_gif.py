"""Build the delivery preview from verified browser screenshots (Pillow required)."""
from pathlib import Path
from PIL import Image, ImageDraw
root=Path(__file__).resolve().parents[1]
frames=[]
for filename,caption in [('desktop-start.png','1. Describe your research request'),('live-desktop-results.png','2. Review 50 companies from live research'),('live-desktop-review.png','3. Verify evidence and approve your introduction')]:
    source=Image.open(root/'docs/verification'/filename).convert('RGB')
    source.thumbnail((960,600))
    canvas=Image.new('RGB',(960,640),'white')
    canvas.paste(source,(0,0))
    ImageDraw.Draw(canvas).text((24,614),caption,fill='#172033')
    frames.append(canvas)
frames[0].save(root/'docs/verification/demo.gif',save_all=True,append_images=frames[1:],duration=[1800,2200,2600],loop=0,optimize=True)
print('Demo GIF created from actual prompt entry and verified live results/review screens.')
