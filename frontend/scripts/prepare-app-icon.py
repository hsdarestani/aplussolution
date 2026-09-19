#!/usr/bin/env python3
import argparse
from pathlib import Path
from PIL import Image, ImageChops, ImageStat

parser = argparse.ArgumentParser()
parser.add_argument("source")
parser.add_argument("output")
parser.add_argument("--background", default="#00142F")
parser.add_argument("--size", type=int, default=1024)
args = parser.parse_args()

src = Image.open(args.source).convert("RGBA")
if min(src.size) < 128:
    raise SystemExit(f"App icon source is unexpectedly small: {src.size}")

def hex_rgb(value: str):
    value = value.strip().lstrip("#")
    if len(value) != 6:
        raise ValueError("background must be RRGGBB")
    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))

bg_rgb = hex_rgb(args.background)
alpha = src.getchannel("A")
alpha_bbox = alpha.point(lambda value: 255 if value > 8 else 0).getbbox()
if not alpha_bbox:
    raise SystemExit("App icon source is fully transparent.")

# Detect the common bad export: a valid icon centered inside an opaque white
# square. Only strip white when the actual outer edge is predominantly white,
# so intentional light artwork inside the icon is preserved.
w, h = src.size
band = max(2, round(min(w, h) * 0.025))
edge_samples = []
pixels = src.load()
for y in range(h):
    for x in range(w):
        if x < band or x >= w-band or y < band or y >= h-band:
            r, g, b, a = pixels[x, y]
            if a > 200:
                edge_samples.append((r, g, b))

edge_is_white = False
if edge_samples:
    white = sum(1 for r, g, b in edge_samples if r >= 238 and g >= 238 and b >= 238)
    edge_is_white = white / len(edge_samples) >= 0.72

bbox = alpha_bbox
if edge_is_white:
    mask = Image.new("L", src.size, 0)
    mp = mask.load()
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a > 8 and not (r >= 238 and g >= 238 and b >= 238):
                mp[x, y] = 255
    content_bbox = mask.getbbox()
    if content_bbox:
        cw = content_bbox[2] - content_bbox[0]
        ch = content_bbox[3] - content_bbox[1]
        if cw >= w * 0.35 and ch >= h * 0.35:
            bbox = content_bbox

# Add a tiny optical breathing room, then make the crop square. This removes
# accidental exported margins without creating another visible frame.
left, top, right, bottom = bbox
bw, bh = right-left, bottom-top
pad = round(max(bw, bh) * 0.012)
left -= pad; top -= pad; right += pad; bottom += pad
side = max(right-left, bottom-top)
cx = (left+right)/2
cy = (top+bottom)/2
left = round(cx-side/2); top = round(cy-side/2)
right = left+side; bottom = top+side

canvas = Image.new("RGBA", (side, side), (*bg_rgb, 255))
src_left = max(0, left); src_top = max(0, top)
src_right = min(w, right); src_bottom = min(h, bottom)
part = src.crop((src_left, src_top, src_right, src_bottom))
canvas.alpha_composite(part, (src_left-left, src_top-top))

result = canvas.convert("RGB").resize((args.size, args.size), Image.Resampling.LANCZOS)
Path(args.output).parent.mkdir(parents=True, exist_ok=True)
result.save(args.output, "PNG", optimize=True)

# Guard against shipping the exact regression reported from installed devices.
check = Image.open(args.output).convert("RGB")
corner = max(8, args.size // 40)
corner_pixels = []
for box in [
    (0,0,corner,corner),
    (args.size-corner,0,args.size,corner),
    (0,args.size-corner,corner,args.size),
    (args.size-corner,args.size-corner,args.size,args.size),
]:
    corner_pixels.extend(list(check.crop(box).getdata()))
white_ratio = sum(1 for r,g,b in corner_pixels if r >= 245 and g >= 245 and b >= 245) / max(1, len(corner_pixels))
if white_ratio > 0.75:
    raise SystemExit(f"Generated icon still has a white outer frame (corner white ratio={white_ratio:.2f}).")

print(f"Prepared app icon {src.size} -> crop {(left, top, right, bottom)} -> {result.size}; edge_white={edge_is_white}; corner_white_ratio={white_ratio:.3f}")
