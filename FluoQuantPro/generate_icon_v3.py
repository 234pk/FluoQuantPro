import math
import random
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance

def create_spindle_icon(size=512):
    # Create a large canvas for anti-aliasing (2x)
    scale = 2
    canvas_size = size * scale
    cx, cy = canvas_size // 2, canvas_size // 2
    
    # 1. Background
    img = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    
    # Mask for rounded corners
    mask = Image.new('L', (canvas_size, canvas_size), 0)
    mask_draw = ImageDraw.Draw(mask)
    corner_radius = int(canvas_size * 0.22)
    mask_draw.rounded_rectangle([0, 0, canvas_size, canvas_size], radius=corner_radius, fill=255)
    
    # Dark Background
    bg = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)
    bg_draw.rectangle([0, 0, canvas_size, canvas_size], fill=(5, 10, 35, 255))
    
    # 2. Spindle Cytoskeleton (Green)
    cyto_layer = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    cyto_draw = ImageDraw.Draw(cyto_layer)
    
    # Spindle Poles (Centrosomes) positions
    # Slightly angled for dynamic look? Or straight? Let's do straight horizontal for clarity.
    pole_dist = canvas_size * 0.35
    pole_left = (cx - pole_dist, cy)
    pole_right = (cx + pole_dist, cy)
    
    # Draw Microtubules (Arcs connecting poles)
    num_lines = 50
    for i in range(num_lines):
        # Normalized position -1 to 1 (vertical distribution)
        t = (i / (num_lines - 1)) * 2 - 1 
        
        # Bulge calculation: more bulge in center lines, less at edges
        # We want an ellipse shape.
        max_bulge = canvas_size * 0.3
        
        # Distribution of arcs
        bulge_y = t * max_bulge
        
        # Add some randomness/waviness
        bulge_y += random.uniform(-5, 5) * scale
        
        # Quadratic Bezier control point
        ctrl_x = cx
        ctrl_y = cy + bulge_y * 1.5 # 1.5 multiplier to make it rounder
        
        # Draw Curve
        points = []
        steps = 40
        for s in range(steps + 1):
            st = s / steps
            bx = (1-st)**2 * pole_left[0] + 2*(1-st)*st * ctrl_x + st**2 * pole_right[0]
            by = (1-st)**2 * pole_left[1] + 2*(1-st)*st * ctrl_y + st**2 * pole_right[1]
            points.append((bx, by))
            
        # Vary opacity based on density
        alpha = random.randint(100, 200)
        width = random.randint(2, 4) * scale
        cyto_draw.line(points, fill=(20, 255, 100, alpha), width=int(width))

    # Draw Centrosomes (Poles) - Bright Glowing Spots
    r_pole = 10 * scale
    for pole in [pole_left, pole_right]:
        # Core
        cyto_draw.ellipse([pole[0]-r_pole, pole[1]-r_pole, pole[0]+r_pole, pole[1]+r_pole], fill=(200, 255, 200, 255))
        
        # Astral rays (short lines radiating out)
        for _ in range(20):
            angle = random.uniform(0, 2*math.pi)
            l = random.uniform(10, 40) * scale
            ex = pole[0] + math.cos(angle) * l
            ey = pole[1] + math.sin(angle) * l
            cyto_draw.line([pole, (ex, ey)], fill=(100, 255, 150, 150), width=int(2*scale))

    # Glow effect for Spindle
    cyto_glow = cyto_layer.filter(ImageFilter.GaussianBlur(radius=6 * scale))
    cyto_layer = Image.alpha_composite(cyto_glow, cyto_layer)

    # 3. Chromosomes (Blue) - Metaphase Plate
    # Vertical alignment in the center
    nuc_layer = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    n_draw = ImageDraw.Draw(nuc_layer)
    
    # Create a cluster of condensed chromosomes
    num_chromosomes = 12
    for _ in range(num_chromosomes):
        # Position: centered in X, spread in Y
        dx = random.uniform(-30, 30) * scale
        dy = random.uniform(-100, 100) * scale
        
        # Shape: Elongated X or rod shape
        cw = random.uniform(15, 25) * scale
        ch = random.uniform(40, 60) * scale
        
        # Rotation
        angle = random.uniform(-30, 30)
        
        # Draw single chromosome on temp image
        temp_c = Image.new('RGBA', (int(cw*2), int(ch*2)), (0,0,0,0))
        tc_draw = ImageDraw.Draw(temp_c)
        # Draw two crossing ellipses for X shape or just one rod
        tc_draw.ellipse([cw/2, 0, cw*1.5, ch*2], fill=(60, 120, 255, 230))
        
        temp_c = temp_c.rotate(angle, resample=Image.Resampling.BICUBIC)
        
        paste_x = int(cx + dx - temp_c.width//2)
        paste_y = int(cy + dy - temp_c.height//2)
        
        nuc_layer.paste(temp_c, (paste_x, paste_y), temp_c)

    # Chromosome Glow
    nuc_glow = nuc_layer.filter(ImageFilter.GaussianBlur(radius=12 * scale))
    # Enhance core brightness
    nuc_core = nuc_layer.filter(ImageFilter.GaussianBlur(radius=2 * scale))
    nuc_final = Image.alpha_composite(nuc_glow, nuc_core)

    # 4. Kinetochores/Puncta (Red)
    # Located on the chromosomes
    puncta_layer = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    p_draw = ImageDraw.Draw(puncta_layer)
    
    for _ in range(20):
        # Near center
        px = cx + random.uniform(-35, 35) * scale
        py = cy + random.uniform(-90, 90) * scale
        pr = random.uniform(4, 7) * scale
        p_draw.ellipse([px-pr, py-pr, px+pr, py+pr], fill=(255, 60, 60, 240))
        
    puncta_glow = puncta_layer.filter(ImageFilter.GaussianBlur(radius=6 * scale))
    puncta_layer = Image.alpha_composite(puncta_glow, puncta_layer)

    # Compose All Layers
    img.paste(bg, (0, 0))
    img = Image.alpha_composite(img, cyto_layer)   # Green Spindle
    img = Image.alpha_composite(img, nuc_final)    # Blue Chromosomes
    img = Image.alpha_composite(img, puncta_layer) # Red Puncta
    
    # 5. Glossy Reflection (Glassmorphism)
    gloss_layer = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gloss_layer)
    # Top reflection
    g_draw.chord([-canvas_size*0.2, -canvas_size*0.2, canvas_size*1.2, canvas_size*0.5], start=180, end=360, fill=(255, 255, 255, 25))
    img = Image.alpha_composite(img, gloss_layer)
    
    # Apply Rounded Mask
    final_img = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    final_img.paste(img, (0, 0), mask=mask)
    
    # Resize to final size
    final_img = final_img.resize((size, size), Image.Resampling.LANCZOS)
    
    return final_img

if __name__ == "__main__":
    print("Generating Spindle Icon...")
    icon = create_spindle_icon(512)
    icon.save("resources/icon.png")
    icon.save("resources/icon.ico", format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("Spindle Icon generated: resources/icon.png, resources/icon.ico")
