"""Batch background remover -> transparent PNG cutouts.
Point it at a folder of raw photos, get clean cutouts out.
This is how you turn 100+ raw drive photos into the cutout library.

    python make_cutouts.py raw_photos cutouts/students

Model 'u2net_human_seg' is tuned for people. Session is reused across the
whole batch for speed (best-practice from the research).
"""
import sys, os, glob
from rembg import remove, new_session
from PIL import Image

def run(src, dst, model="u2net_human_seg"):
    os.makedirs(dst, exist_ok=True)
    session = new_session(model)          # reuse across batch = faster
    files = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG"):
        files += glob.glob(os.path.join(src, ext))
    print(f"{len(files)} photo(s) -> cutting with {model}")
    for f in sorted(files):
        img = Image.open(f).convert("RGBA")
        out = remove(img, session=session)   # alpha_matting off = fast; on = cleaner edges
        name = os.path.splitext(os.path.basename(f))[0] + ".png"
        out.save(os.path.join(dst, name))
        print("  cut:", name)

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "raw_photos"
    dst = sys.argv[2] if len(sys.argv) > 2 else "cutouts/students"
    run(src, dst)
