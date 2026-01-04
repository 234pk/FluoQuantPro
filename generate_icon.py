from PIL import Image, ImageDraw, ImageFilter, ImageFont
import os
import math

def create_icon():
    size = 256
    # 1. Background: Dark Rounded Rect
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw rounded rect background (Dark Gray/Black)
    bg_color = (20, 20, 30, 255)
    padding = 10
    corner_radius = 50
    draw.rounded_rectangle([padding, padding, size-padding, size-padding], radius=corner_radius, fill=bg_color)
    
    # 2. Draw "Cell" glow
    # Center (Nucleus - DAPI Blue)
    cx, cy = size // 2, size // 2
    nucleus_radius = 50
    
    # Radial Gradient for Nucleus
    # We simulate by drawing concentric circles with decreasing alpha
    for r in range(nucleus_radius, 0, -2):
        alpha = int(255 * (1 - (r / nucleus_radius)**2))
        color = (0, 100, 255, alpha)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=color)
        
    # Solid core
    draw.ellipse([cx-20, cy-20, cx+20, cy+20], fill=(100, 200, 255, 255))
    
    # 3. Cytoskeleton (Green - GFP)
    # Draw some wavy ellipses/arcs
    green_color = (0, 255, 100, 150)
    
    # Ellipse 1
    rect1 = [cx-90, cy-70, cx+90, cy+70]
    draw.arc(rect1, start=0, end=360, fill=green_color, width=4)
    
    # Ellipse 2 (Rotated slightly simulation)
    rect2 = [cx-70, cy-90, cx+70, cy+90]
    draw.arc(rect2, start=0, end=360, fill=green_color, width=4)
    
    # 4. Markers (Red dots - RFP)
    red_color = (255, 50, 50, 200)
    dots = [
        (cx+40, cy-40),
        (cx-50, cy+30),
        (cx+20, cy+60),
        (cx-30, cy-50)
    ]
    for dx, dy in dots:
        draw.ellipse([dx-6, dy-6, dx+6, dy+6], fill=red_color)
        # Glow around dot
        draw.ellipse([dx-10, dy-10, dx+10, dy+10], outline=(255, 50, 50, 50), width=2)

    # 5. Overlay Text "FQ" (FluoQuant)
    # Try to load a font, else fallback to simple shapes or none
    # Abstract is better.
    
    # Apply a little blur to whole image to simulate glow?
    # No, keep sharp edges for icon.
    
    # Save
    icon_path_png = os.path.join("resources", "icon.png")
    icon_path_ico = os.path.join("resources", "icon.ico")
    
    img.save(icon_path_png)
    img.save(icon_path_ico, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    
    print(f"Icon generated: {icon_path_png} and {icon_path_ico}")

if __name__ == "__main__":
    create_icon()
