"""
CourtroomAI demo film: story-driven cut with animated cards, zooms on live footage,
Sarvam narration and an original generated background tone.

Facts in the story come from the Supreme Court judgment (Pooja Ramesh Singh v. Jammu and
Kashmir Bank Ltd., 2 July 2026; Indian Kanoon doc 113338666) and the Stanford RegLab/HAI
study headline. Every number on the results card is read from the newest eval/results file.

Needs: video/frames/* from record.py, SARVAM_API_KEY in .env.
Outputs (video/build/): CourtroomAI_film.mp4, CourtroomAI_film_silent.mp4, CourtroomAI_film.srt,
FILM_SCRIPT.md (narration with timings, to re-record in your own voice).

Usage: python video/cinematic.py [--voice shubh_en_narration] [--open-voice rustom_en_suspense]
"""

import argparse
import base64
import json
import math
import os
import subprocess
import urllib.request
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FR = ROOT / "video" / "frames"
OUT = ROOT / "video" / "build"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS, SR = 1920, 1080, 30, 44100

INK, BODY, MUTED = (20, 24, 33), (69, 76, 89), (138, 146, 160)
BG, BRAND, GREEN, RED, AMBER = (245, 246, 248), (36, 54, 94), (4, 120, 87), (190, 18, 60), (180, 83, 9)
NIGHT = (10, 12, 18)

SANS = "/System/Library/Fonts/HelveticaNeue.ttc"
SERIF = "/System/Library/Fonts/Supplemental/Georgia.ttf"
SERIF_I = "/System/Library/Fonts/Supplemental/Georgia Italic.ttf"
MONO = "/System/Library/Fonts/SFNSMono.ttf"


def font(path, size, index=0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except OSError:
        return ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", size)


F = {
    "h1": font(SANS, 84, 1), "h2": font(SANS, 60, 1), "h3": font(SANS, 40, 1), "body": font(SANS, 34), "small": font(SANS, 26),
    "quote": font(SERIF_I, 52), "quote_s": font(SERIF_I, 42), "serif": font(SERIF, 40), "mono": font(MONO, 40), "mono_s": font(MONO, 28),
    "huge": font(SANS, 220, 1), "cap": font(SANS, 34, 1),
}


# ---------------------------------------------------------------- helpers
def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def blank(color=BG):
    return Image.new("RGB", (W, H), color)


def text_center(d, y, s, f, fill, alpha=1.0, bg=None):
    tw = d.textlength(s, font=f)
    col = tuple(int(c * alpha + (bg or BG)[i] * (1 - alpha)) for i, c in enumerate(fill)) if alpha < 1 else fill
    d.text(((W - tw) / 2, y), s, font=f, fill=col)


def wrap(d, s, f, width):
    words, lines, cur = s.split(), [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def vignette(im, strength=0.35):
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([-W * 0.25, -H * 0.35, W * 1.25, H * 1.35], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(220))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(im, Image.blend(im, dark, strength), mask)


def stamp(im, s, color, cx, cy, t, angle=-6):
    """Rubber stamp that drops in (scale 1.6 -> 1.0) and settles."""
    p = ease(t / 0.35)
    if p <= 0:
        return im
    sc = 1.6 - 0.6 * p
    f = font(SANS, int(54 * sc), 1)
    tmp = Image.new("RGBA", (900, 220), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    tw = td.textlength(s, font=f)
    x0, y0 = (900 - tw) / 2 - 26, 110 - 52 * sc
    td.rounded_rectangle([x0, y0, x0 + tw + 52, y0 + 104 * sc], radius=14, outline=color + (int(255 * p),), width=int(7 * sc))
    td.text((x0 + 26, y0 + 18 * sc), s, font=f, fill=color + (int(255 * p),))
    tmp = tmp.rotate(angle, resample=Image.BICUBIC, expand=False)
    im.paste(tmp, (int(cx - 450), int(cy - 110)), tmp)
    return im


def check(d, x, y, size, color):
    """Tick drawn as lines (the UI fonts have no check-mark glyph)."""
    w_ = max(4, size // 7)
    d.line([(x + size * 0.12, y + size * 0.55), (x + size * 0.42, y + size * 0.82), (x + size * 0.9, y + size * 0.2)], fill=color, width=w_, joint="curve")


def scales(d, cx, cy, size, color):
    """Scales-of-justice icon drawn with shapes."""
    s_, w_ = size, max(3, size // 14)
    d.line([(cx, cy - s_ * 0.42), (cx, cy + s_ * 0.38)], fill=color, width=w_)
    d.line([(cx - s_ * 0.4, cy - s_ * 0.28), (cx + s_ * 0.4, cy - s_ * 0.28)], fill=color, width=w_)
    d.line([(cx - s_ * 0.2, cy + s_ * 0.38), (cx + s_ * 0.2, cy + s_ * 0.38)], fill=color, width=w_)
    for sx in (-1, 1):
        px = cx + sx * s_ * 0.4
        d.line([(px, cy - s_ * 0.28), (px - s_ * 0.14, cy + s_ * 0.05)], fill=color, width=w_ // 2 + 1)
        d.line([(px, cy - s_ * 0.28), (px + s_ * 0.14, cy + s_ * 0.05)], fill=color, width=w_ // 2 + 1)
        d.chord([px - s_ * 0.16, cy - s_ * 0.06, px + s_ * 0.16, cy + s_ * 0.16], 0, 180, fill=color)


def caption(im, s):
    d = ImageDraw.Draw(im, "RGBA")
    f = F["cap"]
    tw = d.textlength(s, font=f)
    x0, y0 = (W - tw) / 2 - 30, H - 120
    d.rounded_rectangle([x0, y0, x0 + tw + 60, y0 + 70], radius=18, fill=(20, 24, 33, 220))
    d.text((x0 + 30, y0 + 15), s, font=f, fill=(255, 255, 255))
    return im


def live_badge(im):
    d = ImageDraw.Draw(im, "RGBA")
    f = font(SANS, 20, 1)
    d.rounded_rectangle([18, 16, 228, 52], radius=12, fill=(4, 120, 87, 225))
    d.ellipse([32, 28, 44, 40], fill=(255, 255, 255))
    d.text((54, 23), "LIVE · real app", font=f, fill=(255, 255, 255))
    return im


# ---------------------------------------------------------------- footage
def seg(names):
    names = names if isinstance(names, list) else [names]
    files, times, off = [], [], 0.0
    for n in names:
        t = json.loads((FR / n / "times.json").read_text())
        files += [FR / n / f"{i:05d}.jpg" for i in range(len(t))]
        times += [x + off for x in t]
        off = (times[-1] + 1 / 6) if times else off
    return files, times


class Footage:
    """Plays recorded frames time-stretched to the scene, with a smooth zoom path."""

    def __init__(self, names, zooms):
        self.files, self.times = seg(names)
        self.span = max(self.times[-1], 0.1)
        self.zooms = zooms  # list of (t_fraction, cx, cy, scale) keyframes, cx/cy in 0..1
        self.cache = {}

    def frame(self, frac):
        t_in = frac * self.span
        j = max(0, min(len(self.times) - 1, int(np.searchsorted(self.times, t_in, side="right") - 1)))
        if j not in self.cache:
            self.cache = {j: Image.open(self.files[j]).convert("RGB").resize((W, H))}
        im = self.cache[j]
        k = self.zooms
        for a, b in zip(k, k[1:]):
            if a[0] <= frac <= b[0]:
                p = ease((frac - a[0]) / max(b[0] - a[0], 1e-6))
                cx, cy, sc = (a[i] + (b[i] - a[i]) * p for i in (1, 2, 3))
                break
        else:
            _, cx, cy, sc = k[-1] if frac > k[-1][0] else k[0]
        cw, ch = W / sc, H / sc
        x0 = min(max(cx * W - cw / 2, 0), W - cw)
        y0 = min(max(cy * H - ch / 2, 0), H - ch)
        return im.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.LANCZOS)


# ---------------------------------------------------------------- scenes
def eval_numbers():
    f = sorted((ROOT / "eval" / "results").glob("eval_*.json"))[-1]
    m = json.loads(f.read_text())["metrics"]
    fake = m["fabricated_citation_catch_rate_brief_verifier_on"]
    aud = m["fabricated_citation_catch_rate_audit"]
    off = m["unsupported_claims_shown_verifier_off"]
    return {"file": f.name, "fk": fake["k"], "fn": fake["n"], "ak": aud["k"], "an": aud["n"],
            "off_pct": round(off["pct"]), "off_k": off["k"], "off_n": off["n"],
            "leaks": m["narrative_leakage_final_output"]["sentences_with_unknown_entities"],
            "cases": m["narrative_leakage_final_output"]["cases"]}


def scene_typewriter(t, d_, lines, dark=True):
    im = blank(NIGHT if dark else BG)
    d = ImageDraw.Draw(im)
    total = sum(len(s) for s, _ in lines)
    shown = int(total * ease(t / max(d_ * 0.55, 0.1)))
    y = H / 2 - len(lines) * 55
    for s, f in lines:
        part = s[:max(0, shown)]
        shown -= len(s)
        tw = d.textlength(s, font=f)
        d.text(((W - tw) / 2, y), part, font=f, fill=(235, 238, 243) if dark else INK)
        if 0 < len(part) < len(s) and int(t * 2) % 2 == 0:
            d.text(((W - tw) / 2 + d.textlength(part, font=f), y), "▌", font=f, fill=(235, 238, 243))
        y += 110
    return vignette(im, 0.5)


def scene_fake_citations(t, d_):
    im = blank(NIGHT)
    d = ImageDraw.Draw(im)
    text_center(d, 150, "The tribunal's order relied on precedents", F["h3"], (220, 224, 232), bg=NIGHT)
    rows = ["“… as held by the Hon’ble Court in ________ v. ________ …”",
            "“… the principle laid down in ________ (20__) __ SCC ___ …”",
            "“… as observed in ________ v. Union of ________ …”"]
    for i, r in enumerate(rows):
        a = ease((t - 0.4 - i * 0.5) / 0.4)
        if a <= 0:
            continue
        y = 300 + i * 200
        d.rounded_rectangle([160, y, W - 640, y + 140], radius=18, fill=(26, 30, 40))
        d.text((200, y + 45), r, font=F["quote_s"], fill=tuple(int(160 + 60 * a) for _ in range(3)))
        if t > 1.2 + i * 0.5:
            im = stamp(im, "NON-EXISTENT", (235, 64, 90), W - 330, y + 70, t - 1.2 - i * 0.5)
            d = ImageDraw.Draw(im)
    d.text((160, H - 90), "Illustration of the pattern. The fake citations themselves are not reproduced.", font=F["small"], fill=(110, 116, 130))
    return vignette(im, 0.45)


def scene_timeline(t, d_):
    im = blank(NIGHT)
    d = ImageDraw.Draw(im)
    pts = [("28 Aug 2024", "NCLT admits insolvency", "order cites fake AI precedents", (235, 238, 243)),
           ("11 Sep 2025", "NCLAT dismisses the appeal", "", (235, 238, 243)),
           ("2 Jul 2026", "Supreme Court sets aside both", "", (120, 220, 170))]
    x0, x1, y = 260, W - 260, 520
    p = ease(t / (d_ * 0.6))
    d.line([x0, y, x0 + (x1 - x0) * p, y], fill=(90, 100, 120), width=6)
    for i, (date, a, b, col) in enumerate(pts):
        x = x0 + (x1 - x0) * i / 2
        if p * 2 + 1e-6 < i:
            continue
        d.ellipse([x - 18, y - 18, x + 18, y + 18], fill=col)
        for k, (s, f, c) in enumerate([(date, F["h3"], col), (a, F["body"], (210, 214, 222)), (b, F["small"], (235, 120, 135))]):
            if s:
                tw = d.textlength(s, font=f)
                d.text((x - tw / 2, y + 50 + k * 56 if k else y - 100), s, font=f, fill=c)
    if t > d_ * 0.7:
        text_center(d, 830, "Almost two years of proceedings, undone.", F["h3"], (235, 238, 243), alpha=ease((t - d_ * 0.7) / 0.6), bg=NIGHT)
    text_center(d, H - 80, "Pooja Ramesh Singh v. Jammu and Kashmir Bank Ltd., Supreme Court of India, Civil Appeal No. 11950 of 2025", F["small"], (110, 116, 130), bg=NIGHT)
    return vignette(im, 0.45)


def scene_quote(t, d_, words, attribution, highlight=(), dark=True):
    im = blank(NIGHT if dark else BG)
    d = ImageDraw.Draw(im)
    lines = wrap(d, words, F["quote"], W - 420)
    n = sum(len(l.split()) for l in lines)
    shown = int(n * ease(t / max(d_ * 0.75, 0.1)))
    y = H / 2 - len(lines) * 42 - 40
    for line in lines:
        x = (W - d.textlength(line, font=F["quote"])) / 2
        for w_ in line.split():
            if shown <= 0:
                break
            hot = any(h in w_.lower() for h in highlight)
            d.text((x, y), w_, font=F["quote"], fill=(255, 196, 120) if hot else ((235, 238, 243) if dark else INK))
            x += d.textlength(w_ + " ", font=F["quote"])
            shown -= 1
        y += 84
    text_center(d, y + 40, attribution, F["small"], (140, 148, 162) if dark else MUTED, bg=NIGHT if dark else BG)
    return vignette(im, 0.45) if dark else im


def scene_stat(t, d_):
    im = blank(NIGHT)
    d = ImageDraw.Draw(im)
    a = ease(t / 0.8)
    text_center(d, 250, "1 in 6", F["huge"], (255, 196, 120), alpha=a, bg=NIGHT)
    text_center(d, 540, "legal AI benchmark queries answered with hallucinations, or worse", F["h3"], (220, 224, 232), alpha=a, bg=NIGHT)
    text_center(d, 610, "(Stanford RegLab / HAI, 2024)", F["small"], (120, 126, 140), alpha=a, bg=NIGHT)
    if t > d_ * 0.45:
        b = ease((t - d_ * 0.45) / 0.8)
        text_center(d, 760, "11:00 pm. Hearing at 10:00 am.", F["h2"], (235, 238, 243), alpha=b, bg=NIGHT)
        text_center(d, 850, "How do you check every line?", F["h2"], (235, 238, 243), alpha=b, bg=NIGHT)
    return vignette(im, 0.45)


def scene_title(t, d_):
    im = blank(BG)
    d = ImageDraw.Draw(im)
    a = ease(t / 0.7)
    d.rounded_rectangle([W / 2 - 60, 280, W / 2 + 60, 400], radius=26, fill=BRAND)
    scales(d, W / 2, 340, 80, (255, 255, 255))
    text_center(d, 450, "CourtroomAI", F["h1"], INK, alpha=a)
    if t > 0.8:
        b = ease((t - 0.8) / 0.7)
        text_center(d, 580, "The AI proposes.  Code verifies.", F["h2"], BRAND, alpha=b)
        text_center(d, 680, "Only what passes a check against its source reaches the brief.", F["body"], BODY, alpha=b)
    return im


def scene_flow(t, d_):
    im = blank(BG)
    d = ImageDraw.Draw(im)
    text_center(d, 140, "Five checks before a sentence reaches you", F["h2"], INK)
    steps = [("Facts", "word for word from the FIR"), ("Sections", "official IPC-to-BNS table, by offence date"),
             ("Judgment", "exists in the library"), ("Quote", "matches the judgment word for word"),
             ("Reviewer", "Nemotron Ultra must quote its evidence, checked too")]
    for i, (a_, b_) in enumerate(steps):
        p = ease((t - 0.3 - i * 0.55) / 0.45)
        if p <= 0:
            continue
        y = 280 + i * 140
        x = 330 + (1 - p) * 80
        d.rounded_rectangle([x, y, x + 1260, y + 112], radius=20, fill=(255, 255, 255), outline=(227, 230, 235), width=2)
        d.ellipse([x + 30, y + 30, x + 82, y + 82], fill=(227, 245, 238))
        check(d, x + 36, y + 36, 40, GREEN)
        d.text((x + 115, y + 22), a_, font=F["h3"], fill=INK)
        d.text((x + 115 + d.textlength(a_ + "   ", font=F["h3"]), y + 30), b_, font=F["body"], fill=BODY)
    return im


def scene_proof(t, d_, ev):
    im = blank(BG)
    d = ImageDraw.Draw(im)
    text_center(d, 120, f"Measured on {ev['cases']} practice cases — not claimed", F["h2"], INK)
    cards = [(f"{ev['fk']}/{ev['fn']}", "planted fake judgments\ncaught in the brief", GREEN),
             (f"{ev['ak']}/{ev['an']}", "fake citations caught\nin citation checks", GREEN),
             (f"{ev['off_pct']}%", "of AI-drafted points removed\nby the checks", RED),
             (str(ev["leaks"]), "unverified names or figures\nin final briefs", BRAND)]
    for i, (big, small, col) in enumerate(cards):
        p = ease((t - 0.3 - i * 0.45) / 0.5)
        if p <= 0:
            continue
        x, y = 150 + i * 420, 330 + (1 - p) * 40
        d.rounded_rectangle([x, y, x + 380, y + 400], radius=26, fill=(255, 255, 255), outline=(227, 230, 235), width=2)
        if "/" in big:
            k, n = big.split("/")
            big = f"{int(int(k) * p)}/{n}"
        elif big.endswith("%"):
            big = f"{int(int(big[:-1]) * p)}%"
        d.text((x + 34, y + 50), big, font=font(SANS, 104, 1), fill=col)
        for k, line in enumerate(small.split("\n")):
            d.text((x + 34, y + 230 + k * 44), line, font=F["small"], fill=BODY)
    text_center(d, 800, "Synthetic FIRs with fictional people · fake citations planted on purpose", F["small"], MUTED)
    text_center(d, 840, f"Source: eval/results/{ev['file']}", F["small"], MUTED)
    return im


def scene_close(t, d_):
    im = blank(BG)
    d = ImageDraw.Draw(im)
    a = ease(t / 0.8)
    text_center(d, 330, "Every sentence,", F["h1"], INK, alpha=a)
    text_center(d, 440, "checked against the source.", F["h1"], BRAND, alpha=a)
    if t > 1.0:
        b = ease((t - 1.0) / 0.8)
        text_center(d, 620, "NVIDIA Nemotron Nano · Super · Ultra   ·   Nebius Token Factory   ·   Tavily", F["body"], BODY, alpha=b)
        text_center(d, 690, "CourtroomAI is a research aid for advocates, not legal advice.", F["small"], MUTED, alpha=b)
    return im


# ---------------------------------------------------------------- audio
def sarvam(text, speaker, path, pace=1.08):
    body = {"text": text, "language_code": "en-IN", "model": "bulbul:v4-flash", "speaker": speaker,
            "speech_sample_rate": SR, "pace": pace}
    req = urllib.request.Request("https://api.sarvam.ai/text-to-speech", data=json.dumps(body).encode(),
                                 headers={"api-subscription-key": os.environ["SARVAM_API_KEY"], "Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=90).read())
    path.write_bytes(base64.b64decode("".join(d["audios"])))
    with wave.open(str(path)) as w:
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
        if w.getnchannels() == 2:
            data = data.reshape(-1, 2).mean(axis=1)
        if w.getframerate() != SR:
            n = int(len(data) * SR / w.getframerate())
            data = np.interp(np.linspace(0, len(data) - 1, n), np.arange(len(data)), data)
    return data


def bed(seconds):
    """Original ambient tone (generated here, no third-party music): soft low chords + slow pulse."""
    t = np.arange(int(seconds * SR)) / SR
    chords = [(110.0, 164.8, 220.0), (98.0, 146.8, 196.0), (87.3, 130.8, 174.6), (98.0, 146.8, 196.0)]
    out = np.zeros_like(t)
    seg_len = 8.0
    for i, ch in enumerate(chords * int(seconds // (seg_len * len(chords)) + 2)):
        s, e = i * seg_len, (i + 1) * seg_len + 2
        m = (t >= s) & (t < e)
        if not m.any():
            continue
        tt = t[m] - s
        env = np.minimum(1, tt / 2) * np.minimum(1, np.maximum(0, (e - s - tt) / 2))
        for f0 in ch:
            out[m] += env * (np.sin(2 * np.pi * f0 * tt) + 0.3 * np.sin(2 * np.pi * 2 * f0 * tt)) / 3
    out += 0.15 * np.sin(2 * np.pi * 55 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * t / 4))
    return 0.06 * out / max(np.abs(out).max(), 1e-6)


# ---------------------------------------------------------------- film
def build_scenes(ev, voice, open_voice):
    return [
        dict(kind="draw", fn=lambda t, d: scene_typewriter(t, d, [("Mumbai.", F["h1"]), ("28 August 2024.", F["h2"])]),
             vo="Mumbai. The twenty-eighth of August, twenty twenty-four.", voice=open_voice, min=4),
        dict(kind="draw", fn=scene_fake_citations,
             vo="A tribunal admits a company into insolvency. Its order relies on precedents that never existed. Generated by A I.", voice=open_voice, min=8),
        dict(kind="draw", fn=scene_timeline,
             vo="An appeal fails. It takes almost two years, and the Supreme Court, to set it all aside.", voice=open_voice, min=7),
        dict(kind="draw", fn=lambda t, d: scene_quote(t, d, "Like the release of methyl isocyanate in the province of law and justice: invisible, insidious, and catastrophic by the time anyone notices.",
                                                      "Supreme Court of India, 2 July 2026, on fake AI precedents", highlight=("methyl", "catastrophic")),
             vo="The Court compared fake A I precedents to the Bhopal gas. Invisible. Insidious. And catastrophic, by the time anyone notices.", voice=voice, min=9),
        dict(kind="draw", fn=lambda t, d: scene_quote(t, d, "It is a misconduct on the part of an advocate to cite such judgments without verification.",
                                                      "Supreme Court of India, Pooja Ramesh Singh v. J&K Bank Ltd., para 7", highlight=("misconduct", "verification")),
             vo="And it declared: citing A I judgments without verification is misconduct.", voice=voice, min=6),
        dict(kind="draw", fn=scene_stat,
             vo="Stanford researchers found legal A I tools hallucinate in one of six queries, or more. So at eleven at night, before a ten A M hearing, how do you check every line?", voice=voice, min=10),
        dict(kind="draw", fn=scene_title, vo="Meet CourtroomAI. The A I proposes. Code verifies.", voice=voice, min=5),
        dict(kind="draw", fn=scene_flow,
             vo="Facts must match the F I R word for word. Sections come from the official table. Every judgment must exist, its quote must match exactly, and Nemotron Ultra must prove support with a quote we check too.", voice=voice, min=12),
        dict(kind="foot", seg="brief_input", cap="A sample FIR · fictional people", zooms=[(0, .27, .5, 1.25), (1, .27, .55, 1.35)],
             vo="Here is a dowry harassment F I R, with fictional names. We act for the defence.", voice=voice, min=5),
        dict(kind="foot", seg="brief_pipeline", cap="NVIDIA Nemotron Nano · Super · Ultra on Nebius Token Factory",
             zooms=[(0, .5, .5, 1.0), (.15, .7, .35, 1.45), (.85, .7, .45, 1.45), (1, .5, .5, 1.0)],
             vo="Nemotron Nano reads the F I R. Sections map by the date of the offence. Nemotron Super drafts, but cannot write the brief. Nemotron Ultra checks every judgment. All on Nebius Token Factory.", voice=voice, min=14),
        dict(kind="foot", seg="brief_result", cap="Every point shows its source", zooms=[(0, .5, .5, 1.0), (.2, .72, .45, 1.35), (.6, .72, .5, 1.35), (1, .5, .5, 1.0)],
             vo="Every fact is highlighted in the F I R. Every judgment shows its exact paragraph and a link. And whatever failed a check is listed, with the reason.", voice=voice, min=13),
        dict(kind="img", imgs=["pdf1.png"], cap="One click: a PDF report with every source",
             vo="One click, and it is a report you can file.", voice=voice, min=4),
        dict(kind="foot", seg=["audit_input", "audit_pipeline"], cap="Check any draft, even one written by another AI",
             zooms=[(0, .28, .5, 1.2), (1, .28, .5, 1.2)],
             vo="Now the reverse. Paste any draft. Even one written by another A I.", voice=voice, min=5),
        dict(kind="foot", seg="audit_result", cap="Verified · not supported · read live with Tavily · fabricated",
             zooms=[(0, .73, .45, 1.3), (.5, .73, .5, 1.3), (1, .73, .55, 1.3)],
             vo="A real case, cited correctly: verified. The same case, twisted: flagged. A case we do not hold is fetched live with Tavily, and checked the same way. And a judgment that never existed: caught.", voice=voice, min=13),
        dict(kind="draw", fn=lambda t, d: scene_proof(t, d, ev),
             vo=f"Across {ev['cases']} practice cases, every planted fake was caught. The checks removed {ev['off_pct']} percent of what the A I drafted, and no unverified name or number reached a brief.", voice=voice, min=11),
        dict(kind="draw", fn=scene_close,
             vo="That tribunal's order took almost two years to undo. Checking a citation should take seconds. CourtroomAI. Every sentence, checked against the source.", voice=voice, min=9),
    ]


def render_scene(s, i, n_frames):
    if s["kind"] == "draw":
        for k in range(n_frames):
            yield s["fn"](k / FPS, n_frames / FPS)
    elif s["kind"] == "img":
        base = Image.open(FR / s["imgs"][0]).convert("RGB")
        base.thumbnail((W, H))
        for k in range(n_frames):
            im = blank((232, 235, 240))
            sc = 1.0 + 0.08 * k / n_frames
            b = base.resize((int(base.width * sc), int(base.height * sc)), Image.LANCZOS)
            im.paste(b, ((W - b.width) // 2, 40 - int(120 * k / n_frames)))
            yield caption(im, s["cap"])
    else:
        fo = Footage(s["seg"], s["zooms"])
        for k in range(n_frames):
            yield live_badge(caption(fo.frame(k / n_frames), s["cap"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="shubh_en_narration")
    ap.add_argument("--open-voice", default="rustom_en_suspense")
    ap.add_argument("--max-seconds", type=float, default=175.0)
    a = ap.parse_args()
    load_dotenv(ROOT / ".env")
    OUT.mkdir(parents=True, exist_ok=True)
    ev = eval_numbers()
    scenes = build_scenes(ev, a.voice, a.open_voice)

    vo_dir = OUT / "film_vo"
    vo_dir.mkdir(exist_ok=True)
    for i, s in enumerate(scenes):
        s["audio"] = sarvam(s["vo"], s["voice"], vo_dir / f"vo{i:02d}.wav")
        s["dur"] = max(len(s["audio"]) / SR + 0.7, s["min"])
    total = sum(s["dur"] for s in scenes)
    print(f"film length {total:.1f}s")
    if total > a.max_seconds:
        raise SystemExit(f"FAIL: {total:.1f}s is over the {a.max_seconds:.0f}s budget (rules: under 3 minutes); shorten narration")

    # audio: narration over the generated bed, bed ducked under speech
    voice_track = np.zeros(int(total * SR) + SR)
    pos = 0
    for s in scenes:
        start = pos + int(0.35 * SR)
        voice_track[start:start + len(s["audio"])] += s["audio"]
        pos += int(s["dur"] * SR)
    voice_track *= 0.85 / max(np.abs(voice_track).max(), 1e-6)  # narration peak at -1.4 dB
    music = bed(len(voice_track) / SR)
    env = np.convolve(np.abs(voice_track), np.ones(SR // 5) / (SR // 5), mode="same")
    duck = 1 - 0.6 * np.clip(env / max(env.max(), 1e-6) * 4, 0, 1)
    mix = voice_track + music * duck
    mix *= 0.89 / max(np.abs(mix).max(), 1e-6)  # final peak at -1 dB, no clipping
    mix_path = OUT / "film_audio.wav"
    with wave.open(str(mix_path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())

    silent = OUT / "CourtroomAI_film_silent.mp4"
    enc = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "19", "-preset", "medium", str(silent)],
                           stdin=subprocess.PIPE)
    prev = None
    for i, s in enumerate(scenes):
        n = int(round(s["dur"] * FPS))
        for k, fr in enumerate(render_scene(s, i, n)):
            if prev is not None and k < 9:  # 0.3 s crossfade from the previous scene
                fr = Image.blend(prev, fr, (k + 1) / 10)
            enc.stdin.write(fr.tobytes())
            last = fr
        prev = last
        print(f"  scene {i + 1}/{len(scenes)} rendered ({s['dur']:.1f}s)")
    enc.stdin.close()
    enc.wait()
    film = OUT / "CourtroomAI_film.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(mix_path), "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(film)], check=True)

    def ts(x, sep=","):
        h, r = divmod(x, 3600); m, s_ = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s_):02d}{sep}{int((s_ % 1) * 1000):03d}"
    t, srt, md = 0.0, [], ["# Film narration", "", f"Length {total:.0f} s. Voice: Sarvam `{a.voice}` (opening: `{a.open_voice}`).",
                           "To use your own voice, read each line at its time over CourtroomAI_film_silent.mp4.", ""]
    for i, s in enumerate(scenes, 1):
        srt += [str(i), f"{ts(t + 0.35)} --> {ts(t + s['dur'] - 0.2)}", s["vo"].replace(" A I", " AI").replace("F I R", "FIR").replace("I P C", "IPC").replace("B N S", "BNS"), ""]
        md += [f"**{ts(t, '.')[3:8]}** ({s['dur']:.0f} s)", "", f"> {s['vo']}", ""]
        t += s["dur"]
    (OUT / "CourtroomAI_film.srt").write_text("\n".join(srt), encoding="utf-8")
    (OUT / "FILM_SCRIPT.md").write_text("\n".join(md), encoding="utf-8")
    print(f"OK: {film.relative_to(ROOT)} ({total:.0f}s), silent copy, SRT and FILM_SCRIPT.md")


if __name__ == "__main__":
    main()
