#!/usr/bin/env python3
"""15-second Tajaly film. The bottle, cap, and printed label are pixels
from the two Zajal photographs. Nothing redraws them.
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
PREVIEW = ROOT / "preview"
WIDE_PATH = ASSETS / "wide.jpg"
ROOM_SRC = ASSETS / "desert-house.jpg"
FONT_AR = ASSETS / "Amiri-Regular.ttf"
FONT_LATIN = ASSETS / "STIXTwoText-Regular.ttf"

W, H = 1920, 1080
FPS = 30
N = 15 * FPS  # 450

# Shot boundaries in frames.
S1 = 4 * FPS          # 0–120
S2 = 11 * FPS         # 120–330
# 330–450 is shot 3


def ease_heavy(t: float) -> float:
    t = float(np.clip(t, 0.0, 1.0))
    if t < 0.5:
        return 16 * t ** 5
    return 1 - ((-2 * t + 2) ** 5) / 2


def ease_out(t: float) -> float:
    t = float(np.clip(t, 0.0, 1.0))
    return 1 - (1 - t) ** 4


def smooth(t: float) -> float:
    t = float(np.clip(t, 0.0, 1.0))
    return t * t * (3 - 2 * t)


def load_rgb(path: Path) -> np.ndarray:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(path)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def largest(mask: np.ndarray, k: int = 1) -> np.ndarray:
    n, lab, stats, _ = cv2.connectedComponentsWithStats((mask > 0).astype(np.uint8), 8)
    if n <= 1:
        return mask
    order = np.argsort(stats[1:, cv2.CC_STAT_AREA])[::-1][:k] + 1
    out = np.zeros_like(mask)
    for i in order:
        if stats[i, cv2.CC_STAT_AREA] > 80:
            out[lab == i] = 255
    return out


def scale_sprite(sprite: np.ndarray, width: int) -> np.ndarray:
    h, w = sprite.shape[:2]
    nh = max(1, int(round(h * (width / w))))
    return cv2.resize(sprite, (width, nh), interpolation=cv2.INTER_AREA if width < w else cv2.INTER_CUBIC)


def blit(dst: np.ndarray, sprite: np.ndarray, x: int, y: int, opacity: float = 1.0) -> None:
    if opacity <= 0.001:
        return
    sh, sw = sprite.shape[:2]
    dh, dw = dst.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(dw, x + sw), min(dh, y + sh)
    if x1 >= x2 or y1 >= y2:
        return
    sx1, sy1 = x1 - x, y1 - y
    src = sprite[sy1:sy1 + (y2 - y1), sx1:sx1 + (x2 - x1)].astype(np.float32)
    a = (src[:, :, 3:4] / 255.0) * opacity
    sub = dst[y1:y2, x1:x2].astype(np.float32)
    sub[:] = sub * (1 - a) + src[:, :, :3] * a
    dst[y1:y2, x1:x2] = np.clip(sub, 0, 255).astype(np.uint8)


def ellipse_shadow(dst: np.ndarray, cx: int, cy: int, rx: int, ry: int, strength: float = 0.4) -> None:
    layer = np.zeros(dst.shape[:2], np.float32)
    cv2.ellipse(layer, (int(cx), int(cy)), (max(1, int(rx)), max(1, int(ry))), 0, 0, 360, 1.0, -1)
    k = max(3, int(rx * 0.9) | 1)
    layer = cv2.GaussianBlur(layer, (k, k), 0)
    dst[:] = np.clip(dst.astype(np.float32) * (1 - strength * layer[..., None]), 0, 255).astype(np.uint8)


def build_room() -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Flipped desert house with the real bottle seated on the bench.
    Returns the plate and the bottle box (x, y, w, h) in plate pixels.
    """
    plate = load_rgb(ROOM_SRC)
    plate = np.ascontiguousarray(plate[:, ::-1])  # light from the left, matching the bottle
    plate = cv2.resize(plate, (W, H), interpolation=cv2.INTER_CUBIC)

    rgba = np.array(Image.open(ASSETS / "bottle-tight.png"))
    bh = 348
    scale = bh / rgba.shape[0]
    bw = int(round(rgba.shape[1] * scale))
    sprite = cv2.resize(rgba, (bw, bh), interpolation=cv2.INTER_AREA)
    base_x, base_y = 1000, 734
    x0, y0 = base_x - bw // 2, base_y - bh
    ellipse_shadow(plate, base_x + 8, base_y + 1, int(bw * 0.46), 11, 0.5)
    blit(plate, sprite, x0, y0, 1.0)
    return plate, (x0, y0, bw, bh)


def linen_mask(room: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(room, cv2.COLOR_RGB2HSV)
    hh, ss, vv = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    # The cloth is a warm olive in the lower right, darker than the wall.
    m = ((hh > 8) & (hh < 42) & (ss > 85) & (vv > 22) & (vv < 155)).astype(np.uint8) * 255
    region = np.zeros_like(m)
    region[760:, 1180:] = 255
    m = cv2.bitwise_and(m, region)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    m = largest(m, 1)
    m = cv2.GaussianBlur(m, (31, 31), 0)
    return m


def stir_linen(room: np.ndarray, mask: np.ndarray, shift: float) -> np.ndarray:
    if abs(shift) < 0.15:
        return room
    h, w = mask.shape
    xs = np.arange(w, dtype=np.float32)
    ys = np.arange(h, dtype=np.float32)
    map_x, map_y = np.meshgrid(xs, ys)
    f = (mask.astype(np.float32) / 255.0)
    # A slow sideways breath. The bench under the cloth does not move:
    # the mask is only the linen.
    map_x = map_x - f * shift
    map_y = map_y - f * shift * 0.22
    warped = cv2.remap(room, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return warped


def build_table() -> np.ndarray:
    """The close table is the still-life photograph. The bottle stays in it."""
    return load_rgb(WIDE_PATH)


def _shadow_and_blit(plate: np.ndarray, sprite: np.ndarray, x: int, y: int, fade: float) -> None:
    if fade <= 0.001:
        return
    sh, sw = sprite.shape[:2]
    sil = np.zeros((sh, sw), np.float32)
    sil[:] = sprite[:, :, 3] / 255.0
    sil = cv2.GaussianBlur(sil, (0, 0), 5.5)
    ox, oy = x + 5, y + 7
    x1, y1 = max(0, ox), max(0, oy)
    x2, y2 = min(plate.shape[1], ox + sw), min(plate.shape[0], oy + sh)
    if x2 > x1 and y2 > y1:
        a = sil[y1 - oy:y1 - oy + (y2 - y1), x1 - ox:x1 - ox + (x2 - x1)] * fade * 0.22
        sub = plate[y1:y2, x1:x2].astype(np.float32)
        sub *= 1 - a[..., None]
        plate[y1:y2, x1:x2] = np.clip(sub, 0, 255).astype(np.uint8)
    blit(plate, sprite, x, y, fade)


def _lay_note(plate, sprite, rest_x, rest_y, width, local_t, t0, t1) -> None:
    """Fade in and ease to rest. No bounce, no scale pop."""
    if local_t < t0:
        return
    dur = t1 - t0
    u = ease_out(min(1.0, (local_t - t0) / dur))
    fade = smooth(min(1.0, (local_t - t0) / (dur * 0.45)))
    sp = scale_sprite(sprite, width)
    x = int(round(rest_x + (1 - u) * -14))
    y = int(round(rest_y + (1 - u) * -18))
    _shadow_and_blit(plate, sp, x, y, fade)


def compose_table(photo: np.ndarray, vanilla, local_t: float) -> np.ndarray:
    """Photograph, plus the vanilla pod on open stone.
    Lychee, rose, and bark are the photograph. The camera reveals them.
    """
    plate = photo.copy()
    # Shot-2 local seconds. Shot 3 passes 7, after the pod has settled.
    _lay_note(plate, vanilla, 36, 1048, 280, local_t, 3.40, 4.25)
    powder_on_stone(plate, local_t)
    return plate


def camera_crop(master: np.ndarray, cx: float, cy: float, view_h: float) -> np.ndarray:
    mh, mw = master.shape[:2]
    view_h = float(view_h)
    view_w = view_h * 16 / 9
    x0 = int(round(cx - view_w / 2))
    y0 = int(round(cy - view_h / 2))
    x0 = int(np.clip(x0, 0, mw - view_w))
    y0 = int(np.clip(y0, 0, mh - view_h))
    x1 = int(round(x0 + view_w))
    y1 = int(round(y0 + view_h))
    crop = master[y0:y1, x0:x1]
    if crop.size == 0:
        raise RuntimeError("empty crop")
    interp = cv2.INTER_AREA if crop.shape[1] >= W else cv2.INTER_CUBIC
    return cv2.resize(crop, (W, H), interpolation=interp)


def make_blobs() -> dict[int, np.ndarray]:
    blobs = {}
    for r in range(1, 8):
        g = np.zeros((r * 2 + 1, r * 2 + 1), np.float32)
        cv2.circle(g, (r, r), r, 1.0, -1)
        g = cv2.GaussianBlur(g, (0, 0), r * 0.45)
        m = g.max() or 1
        blobs[r] = g / m
    return blobs


BLOBS = None


def splat(dst: np.ndarray, x: float, y: float, radius: float, color, alpha: float) -> None:
    r = int(np.clip(round(radius), 1, 7))
    blob = BLOBS[r]
    h, w = blob.shape
    xi, yi = int(x) - r, int(y) - r
    dh, dw = dst.shape[:2]
    x1, y1 = max(0, xi), max(0, yi)
    x2, y2 = min(dw, xi + w), min(dh, yi + h)
    if x1 >= x2 or y1 >= y2:
        return
    sx1, sy1 = x1 - xi, y1 - yi
    a = blob[sy1:sy1 + (y2 - y1), sx1:sx1 + (x2 - x1), None] * alpha
    sub = dst[y1:y2, x1:x2].astype(np.float32)
    col = np.array(color, np.float32)
    sub[:] = sub * (1 - a) + col * a
    dst[y1:y2, x1:x2] = np.clip(sub, 0, 255).astype(np.uint8)


def dust_field(frame: np.ndarray, t: float, rng_seed: int = 11) -> None:
    rng = np.random.default_rng(rng_seed)
    # Hung in the sun. Movement over the whole shot is only a few pixels.
    for i in range(42):
        x = rng.uniform(380, 1680)
        y = rng.uniform(120, 640)
        drift_x = rng.uniform(-8, 14)
        drift_y = rng.uniform(2, 22)
        radius = rng.uniform(1.1, 3.4)
        alpha = rng.uniform(0.10, 0.38)
        # Skip motes that would sit on the label area late in the push.
        splat(
            frame,
            x + drift_x * t,
            y + drift_y * t,
            radius,
            (236, 220, 196),
            alpha * (0.75 + 0.25 * math.sin(t * 1.3 + i)),
        )


def powder_on_stone(plate: np.ndarray, local_t: float) -> None:
    """A little beige powder drifts across the stone and stops. Photo pixels."""
    t0, t1 = 5.35, 6.45
    if local_t < t0:
        return
    u = ease_out(min(1.0, (local_t - t0) / (t1 - t0)))
    fade = smooth(min(1.0, (local_t - t0) / 0.4))
    rng = np.random.default_rng(19)
    for _ in range(40):
        x = rng.uniform(90, 460) + rng.uniform(10, 36) * u
        y = rng.uniform(1105, 1260)
        splat(plate, x, y, rng.uniform(1.0, 2.0), (168, 148, 122), rng.uniform(0.35, 0.7) * fade)


def draw_text(frame: np.ndarray, local_t: float) -> None:
    """Shot 3, after the camera has settled. Centered on the stone.
    The words agree with the label that is readable in the same frame:
    تَجَلّي, then ZAJAL, then 50 ML.
    """
    cues = [
        ("ar", "تَجَلّي", 1.20, 1.70),
        ("latin", "ZAJAL", 2.25, 2.70),
        ("small", "50 ML", 3.25, 3.60),
    ]
    visible = []
    for kind, text, t0, t1 in cues:
        if local_t < t0:
            continue
        fade = smooth((local_t - t0) / (t1 - t0))
        visible.append((kind, text, fade))
    if not visible:
        return

    base = Image.fromarray(frame).convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_ar = ImageFont.truetype(str(FONT_AR), 68, layout_engine=ImageFont.Layout.RAQM)
    font_lat = ImageFont.truetype(str(FONT_LATIN), 30)
    font_sm = ImageFont.truetype(str(FONT_LATIN), 16)
    ink = (47, 58, 44)
    shadow = (255, 248, 240)

    # On the open stone, left of the bark, clear of the printed label.
    y = 688
    cx = 620
    for kind, text, fade in visible:
        if kind == "ar":
            font = font_ar
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = cx - tw // 2 - bbox[0]
            draw.text((x, y + 1), text, font=font, fill=_fade(shadow, fade * 0.7))
            draw.text((x, y), text, font=font, fill=_fade(ink, fade))
            y += th + 14
        elif kind == "latin":
            y = _tracked(draw, text, cx, y, font_lat, ink, shadow, fade, tracking=16)
            y += 12
        else:
            y = _tracked(draw, text, cx, y, font_sm, ink, shadow, fade * 0.92, tracking=5)
    frame[:] = np.array(Image.alpha_composite(base, overlay).convert("RGB"))


def _fade(rgb, fade: float):
    return tuple(int(c) for c in rgb) + (int(255 * fade),)


def _tracked(draw, text, cx, y, font, ink, shadow, fade, tracking) -> int:
    widths = [font.getlength(ch) for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x = cx - total / 2
    fill = _fade(ink, fade)
    soft = _fade(shadow, fade * 0.45)
    for ch, w in zip(text, widths):
        draw.text((x, y + 1), ch, font=font, fill=soft)
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + tracking
    bbox = font.getbbox(text)
    return y + (bbox[3] - bbox[1])


def shot1_frame(room: np.ndarray, linen: np.ndarray, bottle_box, frame_i: int) -> np.ndarray:
    t = frame_i / S1  # 0–1
    e = ease_heavy(t)
    # Slow push toward the bottle. 4 seconds, heavy air.
    bx, by, bw, bh = bottle_box
    bcx, bcy = bx + bw / 2, by + bh / 2
    cx = W / 2 + (bcx - W / 2) * 0.55 * e
    cy = H / 2 + (bcy - H / 2) * 0.45 * e
    view_h = H - (H - 860) * e
    shift = 5.5 * e  # linen, a few pixels across the whole shot
    moved = stir_linen(room, linen, shift)
    frame = camera_crop(moved, cx, cy, view_h)
    dust_field(frame, t)
    return frame


def _keys(local_t: float, keys):
    if local_t <= keys[0][0]:
        return keys[0][1], keys[0][2], keys[0][3]
    for a, b in zip(keys, keys[1:]):
        if local_t <= b[0]:
            u = ease_heavy((local_t - a[0]) / (b[0] - a[0]))
            return (
                a[1] + (b[1] - a[1]) * u,
                a[2] + (b[2] - a[2]) * u,
                a[3] + (b[3] - a[3]) * u,
            )
    return keys[-1][1], keys[-1][2], keys[-1][3]


def shot2_camera(local_t: float) -> tuple[float, float, float]:
    # Photo pixels. Each move eases out and stops on a note.
    keys = [
        (0.00, 548, 385, 420),   # wooden cap and amber juice
        (0.40, 548, 385, 420),
        (1.15, 340, 860, 530),   # the split lychee
        (1.90, 340, 860, 530),
        (2.60, 700, 470, 490),   # the rose
        (3.30, 700, 470, 490),
        (4.05, 230, 1140, 430),  # the vanilla pod on the stone
        (4.85, 230, 1140, 430),
        (5.60, 760, 1070, 450),  # the bark
        (6.25, 760, 1070, 450),
        (7.00, 548, 378, 400),   # hold on the cap and the juice
    ]
    return _keys(local_t, keys)


def shot3_camera(local_t: float) -> tuple[float, float, float]:
    e = ease_heavy(min(1.0, local_t / 1.05))
    # From the hold on the cap back until the printed label can be read.
    cx = 548
    cy = 378 + (923 - 378) * e
    view_h = 400 + (607 - 400) * e
    return cx, cy, view_h


def render_frame(i: int, room, linen, box1, photo, vanilla) -> np.ndarray:
    if i < S1:
        return shot1_frame(room, linen, box1, i)
    if i < S2:
        local = (i - S1) / FPS
        plate = compose_table(photo, vanilla, local)
        cx, cy, view_h = shot2_camera(local)
        return camera_crop(plate, cx, cy, view_h)
    local = (i - S2) / FPS
    plate = compose_table(photo, vanilla, 7.0)
    cx, cy, view_h = shot3_camera(local)
    frame = camera_crop(plate, cx, cy, view_h)
    draw_text(frame, local)
    return frame


def write_audio(path: Path) -> None:
    sr = 48000
    n = int(15.0 * sr)
    rng = np.random.default_rng(8)
    white = rng.normal(0, 1, n).astype(np.float32)
    brown = np.cumsum(white)
    brown -= brown.mean()
    brown /= np.max(np.abs(brown)) + 1e-6
    # A slow one-pole lowpass, so the room is a hush and not a hiss.
    room = np.empty_like(brown)
    acc = 0.0
    for i, s in enumerate(brown):
        acc = acc * 0.985 + s * 0.015
        room[i] = acc
    room /= np.max(np.abs(room)) + 1e-6
    room *= 0.012

    def pluck(freq: float, dur: float, decay: float = 0.9965) -> np.ndarray:
        period = max(2, int(sr / freq))
        buf = rng.uniform(-1, 1, period).astype(np.float32)
        out = np.zeros(int(dur * sr), np.float32)
        for i in range(len(out)):
            out[i] = buf[i % period]
            nxt = decay * 0.5 * (buf[i % period] + buf[(i + 1) % period])
            buf[i % period] = nxt
        # Warm it: a short average, like a gut string rather than a click.
        kernel = np.array([0.15, 0.7, 0.15], np.float32)
        out = np.convolve(out, kernel, mode="same")
        env = np.linspace(1, 0.2, len(out)).astype(np.float32)
        attack = np.minimum(1, np.arange(len(out)) / int(0.012 * sr))
        return out * env * attack

    # One quiet phrase. Bayati-coloured, sparse, never in the way of the picture.
    phrase = [(0.7, 146.83), (3.1, 164.81), (5.6, 174.61), (8.4, 196.00), (11.2, 164.81), (13.1, 146.83)]
    oud = np.zeros(n, np.float32)
    for when, freq in phrase:
        tone = pluck(freq, 3.6) * 0.055
        start = int(when * sr)
        end = min(n, start + len(tone))
        oud[start:end] += tone[: end - start]
    mix = room + oud
    peak = np.max(np.abs(mix)) + 1e-6
    # Keep the pictures in front. Peak sits near -23 dBFS.
    mix *= min(1.0, 0.07 / peak)
    pcm = np.clip(mix * 32767, -32767, 32767).astype(np.int16)
    import wave
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def save_preview(name: str, frame: np.ndarray) -> None:
    Image.fromarray(frame).save(PREVIEW / name, quality=90)


def main() -> None:
    global BLOBS
    BLOBS = make_blobs()
    PREVIEW.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    full = "--full" in sys.argv
    print("building room")
    # bottle-tight.png is produced before this script if missing
    if not (ASSETS / "bottle-tight.png").exists():
        raise SystemExit("missing bottle-tight.png")
    room, box1 = build_room()
    linen = linen_mask(room)
    print("linen coverage", round(float((linen > 20).mean()), 4))
    print("building table")
    photo = build_table()
    vanilla = np.array(Image.open(ASSETS / "vanilla-sprite.png"))
    print("table", photo.shape, "vanilla", vanilla.shape)

    # Storyboard
    samples = {
        "f000-wide.jpg": 0,
        "f060-push.jpg": 60,
        "f119-push-end.jpg": 119,
        "f120-table.jpg": 120,
        "f160-lychee.jpg": 160,
        "f210-rose.jpg": 210,
        "f260-vanilla.jpg": 260,
        "f300-blossom.jpg": 300,
        "f329-hold.jpg": 329,
        "f360-back.jpg": 360,
        "f400-name.jpg": 400,
        "f449-end.jpg": 449,
    }
    print("storyboard")
    for name, idx in samples.items():
        frame = render_frame(idx, room, linen, box1, photo, vanilla)
        save_preview(name, frame)
        print(" ", name)

    if not full:
        print("preview only")
        return

    audio = ROOT / "room-oud.wav"
    write_audio(audio)
    out = ROOT / "zajal-tajaly-15s.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "pipe:0",
        "-i", str(audio),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", "-preset", "medium",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        "-shortest",
        str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for i in range(N):
        frame = render_frame(i, room, linen, box1, photo, vanilla)
        proc.stdin.write(frame.tobytes())
        if i % 30 == 0:
            print(f"frame {i}/{N}")
    proc.stdin.close()
    code = proc.wait()
    if code != 0:
        raise SystemExit(f"ffmpeg exited {code}")
    print("wrote", out)


if __name__ == "__main__":
    main()
