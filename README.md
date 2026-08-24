# Featured-Image Tool (prototype)

Auto-generate blog featured images for many domains.
**Design lives in the template PNG. Python only pastes cutout + writes headline.**

Stack: **Pillow** (engine) + **rembg** (batch cutouts) + **JSON config** + **local fonts**.
No AI cost. Human stays in the loop before publish.

## Pipeline
```
raw photo --(rembg)--> transparent cutout
                                   \
template PNG + logo + cutout + headline --(Pillow)--> 1024x468 .webp
```

## Files
```
config/templates.json   all the DATA: domains, colours, template zones, category->folder
engine.py               the compositing engine
make_cutouts.py         batch background remover (raw photos -> cutouts)
make_demo_assets.py     builds DEMO backgrounds/logos/test photo (replace with real ones)
templates/              template BACKGROUND pngs (make these in Photoshop) + logos
cutouts/<category>/     transparent PNG library, by type
fonts/headline.ttf      brand font (swap for Inter / your banner font)
output/                 generated banners
```

## Use
```bash
# 1. build the cutout library once (repeat when new photos come)
python make_cutouts.py raw_photos cutouts/students

# 2. generate a banner
python engine.py --domain edunews --template news --category news \
    --title "NEET UG 2026 Round 1 Seat Allotment Out Now" \
    --highlight "NEET UG 2026" --out output/post123.webp
```

## Phase 1 browser editor
```bash
python -m pip install -r requirements.txt
python app.py
```
Open `http://127.0.0.1:5050`. The editor provides a live preview, domain/template
picker, cutout picker, and WebP/PNG export. It is local-only; publishing remains
human-gated.

## Add a new domain / template
Just add a row in `config/templates.json` (colours, font, template zones) and drop
its background PNG in `templates/`. **No code change.** (MatSpell "data not code" rule.)

## What is DEMO here vs REAL in production
- Template backgrounds + logos in `templates/` are rough stand-ins built by
  `make_demo_assets.py`. **Replace with your real Photoshop PNG templates** — then
  output looks exactly like your live banners.
- `raw_photos/student1.jpg` is a fake test subject. **Use your real Icedrive photos.**
- `fonts/headline.ttf` is DejaVu Bold. **Swap for your brand headline font.**

## Notes / best practices baked in
- rembg reuses one session across the batch (faster). Model `u2net_human_seg` for people;
  try `birefnet-portrait` for cleaner edges, or `-a` alpha matting for hair.
- Fonts are local (no CDN dependency).
- Output is WebP (light, like the live blog). A PNG copy is saved for quick preview.
- Headline auto-shrinks to fit; `--highlight "words"` puts them in the brand highlight box.

## For MatSpell integration (later)
- Move `config/templates.json` into DB rows (Decision: everything is data).
- Photo folder = synced copy of the Icedrive "Website photos" folder (WebDAV nightly sync).
- Engine is called from service layer; writer approves/swaps photo in UI; **publish stays human-gated**.
