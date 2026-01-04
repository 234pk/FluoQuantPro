import math
import random
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

def create_glowing_icon(size=512):
    # Create a large canvas for anti-aliasing (2x)
    scale = 2
    canvas_size = size * scale
    
    # 1. Background: Deep dark blue/black gradient
    # Radial gradient from dark blue to black
    img = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Draw rounded rectangle container (mask)
    mask = Image.new('L', (canvas_size, canvas_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    corner_radius = int(canvas_size * 0.22)
    mask_draw.rounded_rectangle([0, 0, canvas_size, canvas_size], radius=corner_radius, fill=255)
    
    # Background fill
    # Create a radial gradient manually
    bg = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 10, 255))
    for i in range(canvas_size // 2, 0, -2):
        alpha = int(255 * (1 - (i / (canvas_size / 2))**2))
        # Center glow (Deep Blue)
        c_r = 10
        c_g = 20
        c_b = 60
        # Edge is black (0,0,10)
        
        # We simulate radial gradient by drawing concentric circles? 
        # Easier: Just a solid dark blue with a lighter center
        pass
    
    # Let's just do a solid dark background with some noise
    bg_draw = ImageDraw.Draw(bg)
    bg_draw.rectangle([0, 0, canvas_size, canvas_size], fill=(5, 10, 30, 255))
    
    # 2. Cytoskeleton (Green Microtubules) - Layer 1
    # We draw lines and then blur them to create glow
    cyto_layer = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    cyto_draw = ImageDraw.Draw(cyto_layer)
    
    center_x, center_y = canvas_size // 2, canvas_size // 2
    
    for i in range(15):
        # Random bezier-like curves radiating from center area
        angle = random.uniform(0, 2 * math.pi)
        length = random.uniform(canvas_size * 0.3, canvas_size * 0.6)
        
        start_x = center_x + random.uniform(-50, 50)
        start_y = center_y + random.uniform(-50, 50)
        
        end_x = center_x + math.cos(angle) * length
        end_y = center_y + math.sin(angle) * length
        
        # Control point for curve
        ctrl_x = (start_x + end_x) / 2 + random.uniform(-100, 100)
        ctrl_y = (start_y + end_y) / 2 + random.uniform(-100, 100)
        
        # Draw curve using line segments
        points = []
        steps = 20
        for t in range(steps + 1):
            t_norm = t / steps
            x = (1 - t_norm)**2 * start_x + 2 * (1 - t_norm) * t_norm * ctrl_x + t_norm**2 * end_x
            y = (1 - t_norm)**2 * start_y + 2 * (1 - t_norm) * t_norm * ctrl_y + t_norm**2 * end_y
            points.append((x, y))
        
        cyto_draw.line(points, fill=(0, 255, 100, 180), width=int(8 * scale))
        
    # Glow effect for Cytoskeleton
    cyto_glow = cyto_layer.filter(ImageFilter.GaussianBlur(radius=15 * scale))
    cyto_layer = Image.alpha_composite(cyto_glow, cyto_layer) # Combine glow + core
    
    # 3. Nucleus (Blue DAPI)
    nucleus_layer = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    n_draw = ImageDraw.Draw(nucleus_layer)
    
    n_radius = int(canvas_size * 0.25)
    n_x1 = center_x - n_radius
    n_y1 = center_y - n_radius
    n_x2 = center_x + n_radius
    n_y2 = center_y + n_radius
    
    # Outer Glow
    n_draw.ellipse([n_x1, n_y1, n_x2, n_y2], fill=(40, 100, 255, 100))
    nucleus_glow = nucleus_layer.filter(ImageFilter.GaussianBlur(radius=20 * scale))
    
    # Inner Core
    nucleus_core = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    nc_draw = ImageDraw.Draw(nucleus_core)
    nc_draw.ellipse([n_x1 + 20, n_y1 + 20, n_x2 - 20, n_y2 - 20], fill=(100, 180, 255, 220))
    nucleus_core = nucleus_core.filter(ImageFilter.GaussianBlur(radius=5 * scale))
    
    nucleus_final = Image.alpha_composite(nucleus_glow, nucleus_core)
    
    # 4. Puncta (Red Dots)
    puncta_layer = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    p_draw = ImageDraw.Draw(puncta_layer)
    
    for _ in range(20):
        px = center_x + random.uniform(-canvas_size*0.4, canvas_size*0.4)
        py = center_y + random.uniform(-canvas_size*0.4, canvas_size*0.4)
        pr = random.uniform(5 * scale, 12 * scale)
        p_draw.ellipse([px-pr, py-pr, px+pr, py+pr], fill=(255, 50, 50, 200))
        
    puncta_glow = puncta_layer.filter(ImageFilter.GaussianBlur(radius=8 * scale))
    puncta_layer = Image.alpha_composite(puncta_glow, puncta_layer)

    # Compose layers
    # BG -> Cyto -> Nucleus -> Puncta
    img.paste(bg, (0, 0))
    img = Image.alpha_composite(img, cyto_layer)
    img = Image.alpha_composite(img, nucleus_final)
    img = Image.alpha_composite(img, puncta_layer)
    
    # 5. Glossy Overlay (Glassmorphism)
    gloss_layer = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gloss_layer)
    
    # Top-left reflection
    g_draw.chord([ -canvas_size*0.5, -canvas_size*0.2, canvas_size*1.5, canvas_size*0.6], start=180, end=360, fill=(255, 255, 255, 30))
    
    img = Image.alpha_composite(img, gloss_layer)
    
    # Apply Mask (Rounded Corners)
    final_img = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    final_img.paste(img, (0, 0), mask=mask)
    
    # Resize to target size (High Quality Downsampling)
    final_img = final_img.resize((size, size), Image.Resampling.LANCZOS)
    
    return final_img

if __name__ == "__main__":
    icon = create_glowing_icon(512)
    icon.save("resources/icon.png")
    icon.save("resources/icon.ico", format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("Enhanced Glowing Icon generated: resources/icon.png, resources/icon.ico")
