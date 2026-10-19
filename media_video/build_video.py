#!/usr/bin/env python3
"""Build a 60-second kinetic-typography film for JIO TERMINATOR."""

from __future__ import annotations

import math
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "jio-terminator-60s.mp4"
VOICE = ROOT / "narration-fr-v2.mp3"
W, H, FPS, SECONDS = 1280, 720, 24, 60
FRAMES = FPS * SECONDS
INK = (17, 20, 32)
PAPER = (246, 243, 235)
WHITE = (255, 255, 252)
LIME = (202, 255, 88)
VIOLET = (101, 84, 255)
CORAL = (255, 108, 83)
MINT = (83, 228, 195)
SLATE = (100, 107, 119)
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def font(size: int, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_MONO if mono else FONT_BOLD if bold else FONT, size)


def fade_color(color: tuple[int, int, int], alpha: float) -> tuple[int, int, int, int]:
    return (*color, int(255 * max(0, min(1, alpha))))


def text(
    draw: ImageDraw.ImageDraw,
    xy,
    value: str,
    size: int,
    color,
    *,
    bold=False,
    mono=False,
    anchor=None,
    spacing=5,
):
    draw.multiline_text(
        xy,
        value,
        font=font(size, bold, mono),
        fill=color,
        anchor=anchor,
        spacing=spacing,
    )


def rounded(draw, box, fill, outline=None, radius=18, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def enter(p: float, delay: float = 0.0, duration: float = 0.24) -> float:
    return ease((p - delay) / duration)


def draw_brand(draw, accent, p, dark=True):
    fg = WHITE if dark else INK
    alpha = enter(p, 0.02, 0.25)
    # Small, consistent brand mark — not a dashboard header.
    draw.rounded_rectangle(
        (62, 44, 99, 81), radius=11, outline=fade_color(accent, alpha), width=2
    )
    text(draw, (80, 62), "J", 21, fade_color(fg, alpha), bold=True, anchor="mm")
    text(
        draw,
        (116, 51),
        "JIO TERMINATOR",
        15,
        fade_color(fg, alpha),
        bold=True,
        mono=True,
    )


def finish(im: Image.Image, background: tuple[int, int, int]) -> Image.Image:
    """Composite animated RGBA drawing layers onto their solid scene color."""
    base = Image.new("RGBA", im.size, (*background, 255))
    return Image.alpha_composite(base, im).convert("RGB")


def scene_frame(index: int, p: float) -> Image.Image:
    """One bold full-frame scene; p is normalized to [0, 1]."""
    p = max(0.0, min(1.0, p))
    if index == 0:
        im = Image.new("RGBA", (W, H), (*INK, 255))
        d = ImageDraw.Draw(im, "RGBA")
        draw_brand(d, LIME, p, True)
        a = enter(p, 0.05, 0.3)
        text(
            d,
            (72, 176 + int(28 * (1 - a))),
            "L'IA\nSE TROMPE.",
            91,
            fade_color(WHITE, a),
            bold=True,
            spacing=-2,
        )
        # One large interrupted ring: uncertainty made visual, with real motion.
        cx, cy = 960, 345
        r = 145 + int(8 * math.sin(p * math.tau * 1.4))
        d.arc(
            (cx - r, cy - r, cx + r, cy + r),
            22,
            300 + int(24 * math.sin(p * math.tau)),
            fill=fade_color(LIME, a),
            width=13,
        )
        d.arc(
            (cx - r - 32, cy - r - 32, cx + r + 32, cy + r + 32),
            180 + p * 180,
            315 + p * 180,
            fill=fade_color(VIOLET, a * 0.85),
            width=4,
        )
        text(d, (cx, cy), "?", 128, fade_color(LIME, a), bold=True, anchor="mm")
        line = int(480 * enter(p, 0.36, 0.35))
        if line > 0:
            d.rounded_rectangle(
                (75, 447, 75 + line, 455), radius=4, fill=fade_color(LIME, a)
            )
        text(
            d,
            (75, 486),
            "ALORS, EXIGEONS DES PREUVES.",
            22,
            fade_color((190, 198, 208), enter(p, 0.42, 0.28)),
            bold=True,
            mono=True,
        )
        return finish(im, INK)

    if index == 1:
        im = Image.new("RGBA", (W, H), (*PAPER, 255))
        d = ImageDraw.Draw(im, "RGBA")
        draw_brand(d, VIOLET, p, False)
        a = enter(p, 0.03, 0.27)
        text(
            d,
            (70, 145),
            "UNE DEMANDE\nDEVIENT UN PLAN.",
            65,
            fade_color(INK, a),
            bold=True,
            spacing=-1,
        )
        text(
            d,
            (74, 317),
            "JIO transforme le brief en étapes vérifiables.",
            22,
            fade_color(SLATE, enter(p, 0.16, 0.28)),
        )
        labels = [
            ("01", "DEMANDE", VIOLET),
            ("02", "CRITÈRES", CORAL),
            ("03", "ACTIONS", INK),
        ]
        xs = [72, 472, 872]
        y = 444
        line_end = 92 + int(1040 * enter(p, 0.28, 0.55))
        if line_end > 92:
            d.rounded_rectangle(
                (92, y + 36, line_end, y + 42),
                radius=3,
                fill=fade_color((203, 198, 187), a),
            )
        for i, (num, label, color) in enumerate(labels):
            q = enter(p, 0.24 + i * 0.13, 0.28)
            x = xs[i]
            yy = y + int((1 - q) * 24)
            d.ellipse((x, yy, x + 78, yy + 78), fill=fade_color(color, q))
            text(
                d,
                (x + 39, yy + 39),
                num,
                20,
                fade_color(WHITE, q),
                bold=True,
                mono=True,
                anchor="mm",
            )
            text(
                d,
                (x + 96, yy + 18),
                label,
                25,
                fade_color(INK, q),
                bold=True,
                mono=True,
            )
            if i < 2:
                # Direction marker advances along the route as the scene unfolds.
                mx = x + 340
                d.polygon(
                    [(mx, yy + 30), (mx + 18, yy + 39), (mx, yy + 48)],
                    fill=fade_color(VIOLET, enter(p, 0.35 + i * 0.14, 0.2)),
                )
        text(
            d,
            (74, 590),
            "CLARIFIER  →  CADRER  →  AGIR",
            17,
            fade_color(SLATE, enter(p, 0.48, 0.25)),
            bold=True,
            mono=True,
        )
        return finish(im, PAPER)

    if index == 2:
        im = Image.new("RGBA", (W, H), (*VIOLET, 255))
        d = ImageDraw.Draw(im, "RGBA")
        draw_brand(d, LIME, p, True)
        a = enter(p, 0.02, 0.25)
        text(
            d,
            (70, 145),
            "DES ANGLES\nFORGÉS POUR\nCE BRIEF.",
            66,
            fade_color(WHITE, a),
            bold=True,
            spacing=-1,
        )
        text(
            d,
            (75, 405),
            "Pas de roster fixe. Des critères ciblés.",
            20,
            fade_color((227, 224, 255), enter(p, 0.18, 0.25)),
        )
        cards = [
            ("COUVRIR", "le brief", LIME),
            ("CONTRER", "les hypothèses", CORAL),
            ("PROUVER", "les affirmations", MINT),
        ]
        for i, (verb, detail, color) in enumerate(cards):
            q = enter(p, 0.12 + i * 0.14, 0.28)
            x = 730 + int((1 - q) * 200)
            y = 159 + i * 150
            rounded(
                d,
                (x, y, 1195, y + 113),
                fade_color(INK, q),
                fade_color(color, q),
                radius=19,
                width=2,
            )
            d.ellipse((x + 22, y + 26, x + 62, y + 66), fill=fade_color(color, q))
            text(
                d,
                (x + 82, y + 21),
                verb,
                21,
                fade_color(color, q),
                bold=True,
                mono=True,
            )
            text(d, (x + 82, y + 57), detail, 18, fade_color(WHITE, q))
        text(
            d,
            (75, 636),
            "LES RÔLES SONT DES MANDATS — PAS DES PREUVES.",
            15,
            fade_color(WHITE, enter(p, 0.52, 0.24)),
            bold=True,
            mono=True,
        )
        return finish(im, VIOLET)

    if index == 3:
        im = Image.new("RGBA", (W, H), (*PAPER, 255))
        d = ImageDraw.Draw(im, "RGBA")
        draw_brand(d, CORAL, p, False)
        a = enter(p, 0.02, 0.28)
        text(
            d,
            (70, 145),
            "LA RÉPONSE\nPASSE UN TEST.",
            68,
            fade_color(INK, a),
            bold=True,
            spacing=-1,
        )
        text(
            d,
            (74, 320),
            "Les affirmations sont confrontées au réel.",
            22,
            fade_color(SLATE, enter(p, 0.15, 0.25)),
        )
        # One clean cause-and-check animation: claim, adversarial test, evidence.
        stages = [
            (70, "AFFIRMATION", INK),
            (476, "TEST", CORAL),
            (882, "PREUVE", VIOLET),
        ]
        y = 444
        progress = enter(p, 0.18, 0.62)
        d.rounded_rectangle(
            (136, y + 48, 1144, y + 54), radius=3, fill=fade_color((205, 198, 186), a)
        )
        progressed = int(1008 * progress)
        if progressed > 0:
            d.rounded_rectangle(
                (136, y + 48, 136 + progressed, y + 54),
                radius=3,
                fill=fade_color(CORAL, a),
            )
        for i, (x, label, color) in enumerate(stages):
            q = enter(p, 0.2 + i * 0.15, 0.28)
            yy = y + int((1 - q) * 20)
            rounded(
                d,
                (x, yy, x + 300, yy + 119),
                fade_color(WHITE, q),
                fade_color(color, q),
                radius=17,
                width=3,
            )
            text(
                d,
                (x + 24, yy + 33),
                f"0{i + 1}",
                16,
                fade_color(color, q),
                bold=True,
                mono=True,
            )
            text(
                d,
                (x + 24, yy + 68),
                label,
                21,
                fade_color(INK, q),
                bold=True,
                mono=True,
            )
            if i == 1:
                # X flicks to a check only when the reveal animation arrives.
                cx = x + 263
                cy = yy + 24
                if p < 0.68:
                    d.line(
                        (cx - 8, cy - 8, cx + 8, cy + 8),
                        fill=fade_color(CORAL, q),
                        width=3,
                    )
                    d.line(
                        (cx + 8, cy - 8, cx - 8, cy + 8),
                        fill=fade_color(CORAL, q),
                        width=3,
                    )
                else:
                    t = ease((p - 0.68) / 0.2)
                    d.line(
                        (cx - 8, cy, cx - 1, cy + 7), fill=fade_color(MINT, t), width=4
                    )
                    d.line(
                        (cx - 1, cy + 7, cx + 12, cy - 9),
                        fill=fade_color(MINT, t),
                        width=4,
                    )
        text(
            d,
            (74, 615),
            "EXÉCUTER  ·  OBSERVER  ·  COMPARER",
            17,
            fade_color(SLATE, enter(p, 0.48, 0.25)),
            bold=True,
            mono=True,
        )
        return finish(im, PAPER)

    if index == 4:
        im = Image.new("RGBA", (W, H), (*CORAL, 255))
        d = ImageDraw.Draw(im, "RGBA")
        draw_brand(d, INK, p, False)
        a = enter(p, 0.02, 0.25)
        text(
            d,
            (72, 165),
            "ACCORD\n≠ VÉRITÉ.",
            91,
            fade_color(INK, a),
            bold=True,
            spacing=-4,
        )
        text(
            d,
            (78, 405),
            "Des rôles peuvent partager le même modèle.",
            23,
            fade_color(INK, enter(p, 0.17, 0.22)),
        )
        # Three distinct review paths merge into one shared source: a caveat, not consensus theatre.
        cx, cy = 930, 343
        for i, color in enumerate([INK, VIOLET, MINT]):
            yy = 205 + i * 130
            xstart = 690
            q = enter(p, 0.13 + i * 0.12, 0.3)
            d.line(
                (xstart, yy, cx - int(70 * q), cy), fill=fade_color(color, q), width=5
            )
            d.ellipse(
                (xstart - 22, yy - 22, xstart + 22, yy + 22), fill=fade_color(color, q)
            )
        r = 68
        d.ellipse(
            (cx - r, cy - r, cx + r, cy + r), fill=fade_color(INK, enter(p, 0.5, 0.25))
        )
        text(
            d,
            (cx, cy),
            "1",
            56,
            fade_color(WHITE, enter(p, 0.5, 0.25)),
            bold=True,
            anchor="mm",
        )
        text(
            d,
            (728, 536),
            "UN ANGLE MORT PEUT RESTER PARTAGÉ.",
            15,
            fade_color(INK, enter(p, 0.44, 0.25)),
            bold=True,
            mono=True,
        )
        return finish(im, CORAL)

    # Final scene: uncertainty is explicit; the last four seconds resolve to a clear end card.
    im = Image.new("RGBA", (W, H), (*INK, 255))
    d = ImageDraw.Draw(im, "RGBA")
    draw_brand(d, MINT, p, True)
    content = 1 - ease((p - 0.40) / 0.16)
    outro = ease((p - 0.56) / 0.20)
    a = enter(p, 0.02, 0.25) * content
    text(
        d,
        (70, 165),
        "LE DOUTE\nRESTE VISIBLE.",
        72,
        fade_color(WHITE, a),
        bold=True,
        spacing=-2,
    )
    text(
        d,
        (75, 354),
        "JIO distingue le vérifié de l'incertain.",
        21,
        fade_color((184, 194, 207), a),
    )
    # Honest fork: proceed when supported; abstain when not.
    x0, y0 = 803, 235
    d.line(
        (x0, y0 + 112, x0 + 116, y0 + 112), fill=fade_color((146, 159, 176), a), width=4
    )
    d.line((x0 + 116, y0 + 112, x0 + 190, y0 + 42), fill=fade_color(MINT, a), width=4)
    d.line((x0 + 116, y0 + 112, x0 + 190, y0 + 182), fill=fade_color(CORAL, a), width=4)
    rounded(
        d,
        (x0 + 185, y0 + 2, x0 + 402, y0 + 82),
        fade_color((29, 43, 51), a),
        fade_color(MINT, a),
        radius=15,
        width=2,
    )
    rounded(
        d,
        (x0 + 185, y0 + 142, x0 + 402, y0 + 222),
        fade_color((47, 33, 37), a),
        fade_color(CORAL, a),
        radius=15,
        width=2,
    )
    text(
        d, (x0 + 207, y0 + 29), "ÉTABLI", 20, fade_color(MINT, a), bold=True, mono=True
    )
    text(
        d,
        (x0 + 207, y0 + 169),
        "ABSTENTION",
        17,
        fade_color(CORAL, a),
        bold=True,
        mono=True,
    )
    if outro > 0:
        d.rectangle((0, 0, W, H), fill=fade_color(INK, outro * 0.9))
        alpha = enter(p, 0.62, 0.22)
        # Brand lockup and restrained closing statement.
        d.rounded_rectangle(
            (80, 240, 135, 295), radius=15, outline=fade_color(MINT, alpha), width=3
        )
        text(d, (107, 267), "J", 32, fade_color(WHITE, alpha), bold=True, anchor="mm")
        text(d, (160, 238), "JIO TERMINATOR", 53, fade_color(WHITE, alpha), bold=True)
        closing_width = int(1116 * ease((p - 0.64) / 0.22))
        if closing_width > 0:
            d.rounded_rectangle(
                (82, 340, 82 + closing_width, 348),
                radius=4,
                fill=fade_color(MINT, alpha),
            )
        text(
            d,
            (84, 390),
            "PAS DE ZÉRO ERREUR PROMIS. DES LIMITES VISIBLES.",
            19,
            fade_color((194, 203, 215), alpha),
            bold=True,
            mono=True,
        )
    return finish(im, INK)


def frame_at(frame: int) -> np.ndarray:
    seconds = frame / FPS
    idx = min(5, int(seconds // 10))
    local = seconds - idx * 10
    current = scene_frame(idx, local / 10)
    # Short cross-dissolves, rather than six abrupt title-card cuts.
    if idx > 0 and local < 0.38:
        previous = scene_frame(idx - 1, 1.0)
        current = Image.blend(previous, current, ease(local / 0.38))
    return np.asarray(current, dtype=np.uint8)


def write_score(path: Path) -> None:
    sr = 48000
    n = sr * SECONDS
    t = np.arange(n, dtype=np.float64) / sr
    chord = [73.42, 110.0, 146.83, 220.0]
    pad = sum(
        np.sin(2 * np.pi * f * t + 0.18 * np.sin(2 * np.pi * 0.1 * t + i)) * 0.012
        for i, f in enumerate(chord)
    )
    pad += 0.008 * np.sin(2 * np.pi * 55 * t + 0.2 * np.sin(2 * np.pi * 0.07 * t))
    pulse = np.zeros(n, dtype=np.float64)
    for sec in np.arange(0.3, SECONDS, 1.25):
        start = int(sec * sr)
        length = min(int(0.35 * sr), n - start)
        tt = np.arange(length) / sr
        pulse[start : start + length] += (
            0.026 * np.sin(2 * np.pi * (76 - 24 * tt) * tt) * np.exp(-tt * 10)
        )
    chimes = np.zeros(n, dtype=np.float64)
    for sec in (0.5, 10, 20, 30, 40, 50, 56):
        start = int(sec * sr)
        length = min(int(1.4 * sr), n - start)
        tt = np.arange(length) / sr
        chimes[start : start + length] += (
            0.012
            * (np.sin(2 * np.pi * 659.25 * tt) + 0.5 * np.sin(2 * np.pi * 987.77 * tt))
            * np.exp(-tt * 3)
        )
    fade = np.minimum(1, t / 1.2) * np.minimum(1, (SECONDS - t) / 1.6)
    mono = np.clip((pad + pulse + chimes) * fade, -0.7, 0.7)
    pcm = (np.stack((mono, mono), axis=1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(sr)
        out.writeframes(pcm.tobytes())


def render() -> None:
    if not VOICE.exists():
        raise FileNotFoundError(VOICE)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    silent = ROOT / "video-silent.mp4"
    score = ROOT / "score.wav"
    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{W}x{H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(silent),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for i in range(FRAMES):
            proc.stdin.write(frame_at(i).tobytes())
            if i % (FPS * 10) == 0:
                print(f"Rendu {i // FPS:02d}s / {SECONDS}s", flush=True)
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("encodage vidéo échoué")
    write_score(score)
    mix = "[1:a]volume=0.12,afade=t=out:st=58:d=2[music];[2:a]adelay=120|120,volume=1.2,apad=pad_dur=11[voice];[music][voice]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95[a]"
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(silent),
            "-i",
            str(score),
            "-i",
            str(VOICE),
            "-filter_complex",
            mix,
            "-map",
            "0:v:0",
            "-map",
            "[a]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-t",
            str(SECONDS),
            "-metadata",
            "title=JIO TERMINATOR — Motion design (60 s)",
            "-metadata",
            "artist=JIO TERMINATOR",
            "-metadata:s:a:0",
            "language=fra",
            "-movflags",
            "+faststart",
            str(OUT),
        ],
        check=True,
    )
    silent.unlink(missing_ok=True)
    score.unlink(missing_ok=True)
    print(f"Terminé : {OUT} ({OUT.stat().st_size / 1_000_000:.1f} Mo)")


if __name__ == "__main__":
    render()
