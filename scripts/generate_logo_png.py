"""Generate a PNG logo from the inline SVG polyline definition in app.py."""

from PIL import Image, ImageDraw

SCALE = 20  # 40x32 viewBox → 800x640 canvas
W = 40 * SCALE
H = 32 * SCALE
STROKE = round(2.2 * SCALE)
PADDING = STROKE * 2
BG = (15, 39, 68)          # #0F2744 navy
WHITE = (249, 250, 251)    # #F9FAFB
BLUE = (37, 99, 235)       # #2563EB

def scale_pts(pts):
    return [(x * SCALE + PADDING, y * SCALE + PADDING) for x, y in pts]

white_pts = scale_pts([(0, 32), (11, 6), (20, 20)])
blue_pts  = scale_pts([(20, 20), (29, 2), (40, 32)])

img = Image.new("RGBA", (W + PADDING * 2, H + PADDING * 2), BG + (255,))
draw = ImageDraw.Draw(img)

draw.line(white_pts, fill=WHITE, width=STROKE, joint="curve")
draw.line(blue_pts,  fill=BLUE,  width=STROKE, joint="curve")

# Also save a transparent-background version
img_transparent = Image.new("RGBA", (W + PADDING * 2, H + PADDING * 2), (0, 0, 0, 0))
draw2 = ImageDraw.Draw(img_transparent)
draw2.line(white_pts, fill=WHITE, width=STROKE, joint="curve")
draw2.line(blue_pts,  fill=BLUE,  width=STROKE, joint="curve")

out_dark = "/app/assets/logo_dark.png"
out_transparent = "/app/assets/logo_transparent.png"

img.save(out_dark)
img_transparent.save(out_transparent)
print(f"Saved: {out_dark}")
print(f"Saved: {out_transparent}")
