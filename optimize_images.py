import os
import glob
from PIL import Image

def optimize_image(filepath):
    # Open image
    try:
        with Image.open(filepath) as img:
            # Convert to RGB if needed (for PNG with alpha or P modes)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")
            
            # Target path
            base, ext = os.path.splitext(filepath)
            target_path = base + ".webp"
            
            # Save as WebP
            img.save(target_path, "webp", quality=80, optimize=True)
            print(f"Optimized: {filepath} -> {target_path}")
            
            # Optionally remove original to force template updates, but let's keep it for fallback if needed, or remove it.
            # We will not remove it to be safe.
    except Exception as e:
        print(f"Failed to optimize {filepath}: {e}")

if __name__ == '__main__':
    images = []
    images.extend(glob.glob('app/static/images/**/*.jpg', recursive=True))
    images.extend(glob.glob('app/static/images/**/*.jpeg', recursive=True))
    images.extend(glob.glob('app/static/images/**/*.png', recursive=True))
    
    for img in images:
        optimize_image(img)
