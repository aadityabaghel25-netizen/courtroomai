"""
Assemble the demo video from video/frames (made by record.py).

Outputs in video/build/:
  CourtroomAI_demo.mp4            1920x1080, captions, placeholder voice (macOS "Aman")
  CourtroomAI_demo_silent.mp4     same picture, no audio (for recording your own voiceover)
  CourtroomAI_demo.srt            subtitles (upload to YouTube as captions)
  VOICEOVER.md                    the narration with start times, to read while recording

Numbers on the results card and in the narration are read from the newest
eval/results/eval_*.json; none are typed by hand.

Usage: python video/build.py [--voice Aman] [--rate 172]
"""

import argparse
import glob
import json
import math
import subprocess
import tempfile
import wave
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FR = ROOT / "video" / "frames"
OUT = ROOT / "video" / "build"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
SIZE = (1920, 1080)
FPS = 24
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def eval_numbers():
    files = sorted((ROOT / "eval" / "results").glob("eval_*.json"))
    r = json.loads(files[-1].read_text())
    m = r["metrics"]
    fake = m["fabricated_citation_catch_rate_brief_verifier_on"]
    off = m["unsupported_claims_shown_verifier_off"]
    ci = fake["wilson95"]
    return {
        "file": f"eval/results/{files[-1].name}",
        "n": r["n_cases"], "fake_k": fake["k"], "fake_n": fake["n"],
        "fake_ci": f"{round(100 * ci[0])}–{round(100 * ci[1])}%",
        "off_pct": off["pct"], "off_k": off["k"], "off_n": off["n"],
        "leaks": m["narrative_leakage_final_output"]["sentences_with_unknown_entities"],
    }


def scenes(ev):
    return [
        dict(img="slide1.jpg", cap="CourtroomAI · case research you can check, line by line",
             vo="This is CourtroomAI: case research for Indian advocates that you can check, line by line."),
        dict(img="slide2.jpg", cap="Supreme Court of India: citing unverified AI judgments is misconduct",
             vo="In July 2026, the Supreme Court of India declared that citing AI-generated judgments without verification is misconduct. Because AI research tools can invent case law: a case name that sounds real, a citation that looks real, a quote no judge ever wrote."),
        dict(img="slide3.jpg", cap="Since 1 July 2024: IPC → BNS, CrPC → BNSS, Evidence Act → BSA",
             vo="And since July 2024, India's criminal codes have new section numbers. Which code applies depends on the date of the offence."),
        dict(img="slide4.jpg", cap="The AI proposes. Code verifies. Only what passes reaches the brief.",
             vo="So we flipped the approach. The AI may only propose points, each naming its source. Code checks every point. Only what passes reaches the brief, and everything else is listed with the reason."),
        dict(seg="home", cap="The real app, running live", vo="Let's see it in the real app."),
        dict(seg="brief_input", cap="A sample FIR with fictional people · acting for the defence",
             vo="Here is a sample FIR about dowry harassment, with fictional people. We act for the defence."),
        dict(seg="brief_pipeline", cap="Live pipeline: Nemotron Nano, Super and Ultra on Nebius Token Factory",
             vo="Watch it work. Nemotron Nano reads the FIR. Sections are matched to the new codes from the official table. We search our judgment library. Nemotron Super drafts the points, and Nemotron Ultra, the largest model, reviews every judgment. All of it runs on Nebius Token Factory."),
        dict(seg="brief_result", cap="Every point shows its source · rejected points are listed with the reason",
             vo="Every fact is quoted word for word from the FIR. Hover over one, and it lights up. Sections show their new-law equivalents. Each judgment shows the exact paragraph, matched word for word, with a link to the full text. Later cases come from a live Tavily search. And anything that failed a check is listed, with the reason. Nothing is hidden."),
        dict(imgs=["pdf1.png", "pdf2.png"], cap="One click: a PDF report with every source and link",
             vo="One click gives a clean PDF report, with every source and link."),
        dict(seg=["audit_input", "audit_pipeline"], cap="Check any draft, including one written by another AI tool",
             vo="Now, checking someone else's draft. Paste any draft, even one written by another AI tool."),
        dict(seg="audit_result", cap="Verified · not supported · read from the web with Tavily · fabricated",
             vo="A real case, cited correctly, is verified. The same case, cited for something it never said, is flagged. A case that is not in our library? We fetch the full judgment with Tavily, and check it the same way. And a citation that does not exist anywhere, is caught."),
        dict(img="slide5.jpg", cap=f"Source: {ev['file']}",
             vo=(f"We tested this on {ev['n']} practice cases, each with a fake judgment planted in it. "
                 f"It was caught {ev['fake_k']} times out of {ev['fake_n']}. With the checks switched off, "
                 f"{round(ev['off_pct'])} percent of the drafted points would not have held up, and none of them reached the final brief.")),
        dict(img="slide6.jpg", cap="CourtroomAI · NVIDIA Nemotron · Nebius Token Factory · Tavily",
             vo="CourtroomAI. Built on NVIDIA Nemotron, Nebius Token Factory, and Tavily. Every sentence, checked against the source."),
    ]


def render_slides(ev):
    """Fill the results numbers into the cards and render each card in a fresh headless Chrome."""
    html = (ROOT / "video" / "slides.html").read_text(encoding="utf-8")
    html = (html.replace("__N_CASES__", str(ev["n"])).replace("__FAKE_CAUGHT__", f"{ev['fake_k']}/{ev['fake_n']}")
            .replace("__FAKE_CI__", ev["fake_ci"]).replace("__OFF_UNSUP__", f"{round(ev['off_pct'])}%")
            .replace("__OFF_K__", str(ev["off_k"])).replace("__OFF_N__", str(ev["off_n"]))
            .replace("__LEAKS__", str(ev["leaks"])).replace("__EVAL_FILE__", ev["file"]))
    tmp = OUT / "slides_filled.html"
    tmp.write_text(html, encoding="utf-8")
    chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    for n in range(1, 7):
        subprocess.run([chrome, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1.5",
                        "--window-size=1280,720", "--virtual-time-budget=4000", f"--screenshot={OUT / f'slide{n}.png'}",
                        f"{tmp.as_uri()}#s{n}"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def tts(text, path, voice, rate):
    aiff = path.with_suffix(".aiff")
    subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text], check=True)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(aiff), "-ac", "1", "-ar", "24000", str(path)], check=True)
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def load(path):
    im = Image.open(path).convert("RGB")
    if im.size != SIZE:
        bg = Image.new("RGB", SIZE, (245, 246, 248))
        im.thumbnail(SIZE)
        bg.paste(im, ((SIZE[0] - im.width) // 2, (SIZE[1] - im.height) // 2))
        im = bg
    return im


def caption(im, text, live):
    """Lower-third caption on live footage only; cards carry their own large text (and footnotes)."""
    if not live:
        return im
    d = ImageDraw.Draw(im, "RGBA")
    f = ImageFont.truetype(FONT_B, 34)
    tw = d.textlength(text, font=f)
    x0, y0 = (SIZE[0] - tw) / 2 - 28, SIZE[1] - 112
    d.rounded_rectangle([x0, y0, x0 + tw + 56, y0 + 66], radius=16, fill=(20, 24, 33, 215))
    d.text((x0 + 28, y0 + 13), text, font=f, fill=(255, 255, 255))
    if live:
        fl = ImageFont.truetype(FONT_B, 22)
        cx = SIZE[0] // 2
        d.rounded_rectangle([cx - 131, 24, cx + 131, 66], radius=12, fill=(4, 120, 87, 230))
        d.ellipse([cx - 115, 38, cx - 101, 52], fill=(255, 255, 255))
        d.text((cx - 89, 32), "LIVE · real app", font=fl, fill=(255, 255, 255))
    return im


def seg_frames(names):
    names = names if isinstance(names, list) else [names]
    files, times, offset = [], [], 0.0
    for n in names:
        t = json.loads((FR / n / "times.json").read_text())
        files += [FR / n / f"{i:05d}.jpg" for i in range(len(t))]
        times += [x + offset for x in t]
        offset = times[-1] + 1 / 6 if times else offset
    return files, times


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", default="Aman")
    ap.add_argument("--rate", type=int, default=172)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ev = eval_numbers()
    render_slides(ev)
    sc = scenes(ev)

    tmp = Path(tempfile.mkdtemp(prefix="courtroomai_vo_"))
    durs = []
    for i, s in enumerate(sc):
        s["wav"] = tmp / f"vo{i:02d}.wav"
        vd = tts(s["vo"], s["wav"], a.voice, a.rate)
        s["dur"] = max(vd + 0.8, 3.0)
        durs.append(s["dur"])
    total = sum(durs)
    print(f"total length {total:.1f}s")
    if total > 178:
        print("WARNING: longer than 2:58; shorten narration")

    # Audio track: each scene's voice padded with silence to the scene length.
    full = OUT / "voice_full.wav"
    with wave.open(str(full), "wb") as out:
        out.setnchannels(1); out.setsampwidth(2); out.setframerate(24000)
        for s in sc:
            with wave.open(str(s["wav"])) as w:
                data = w.readframes(w.getnframes())
            pad = int(s["dur"] * 24000) - len(data) // 2
            out.writeframes(data + b"\x00\x00" * max(0, pad))

    silent = OUT / "CourtroomAI_demo_silent.mp4"
    enc = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{SIZE[0]}x{SIZE[1]}", "-r", str(FPS), "-i", "-",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium", str(silent)],
                           stdin=subprocess.PIPE)
    for s in sc:
        n_out = int(round(s["dur"] * FPS))
        if "img" in s or "imgs" in s:
            imgs = [OUT / s["img"].replace(".jpg", ".png")] if "img" in s else [FR / x for x in s["imgs"] if (FR / x).exists()]
            base = [caption(load(p), s["cap"], live=False) for p in imgs]
            for k in range(n_out):
                enc.stdin.write(base[min(len(base) - 1, k * len(base) // n_out)].tobytes())
        else:
            files, times = seg_frames(s["seg"])
            span = max(times[-1], 0.1)
            j, cache = 0, {}
            for k in range(n_out):
                t_in = (k / n_out) * span
                while j + 1 < len(times) and times[j + 1] <= t_in:
                    j += 1
                if j not in cache:
                    cache.clear()
                    cache[j] = caption(load(files[j]), s["cap"], live=True).tobytes()
                enc.stdin.write(cache[j])
    enc.stdin.close()
    enc.wait()

    voiced = OUT / "CourtroomAI_demo.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", str(silent), "-i", str(full), "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "160k", "-shortest", str(voiced)], check=True)

    # Subtitles and voiceover sheet
    def ts(x, sep=","):
        h, r = divmod(x, 3600); m, s_ = divmod(r, 60)
        return f"{int(h):02d}:{int(m):02d}:{int(s_):02d}{sep}{int((s_ % 1) * 1000):03d}"
    t, srt, md = 0.0, [], ["# Voiceover script", "",
                          f"Total length: {total:.0f} s. Read each line when its time comes; pauses are built in.",
                          "Record in a quiet room, phone close to your mouth. Then replace the audio of CourtroomAI_demo_silent.mp4.", ""]
    for i, s in enumerate(sc, 1):
        srt += [str(i), f"{ts(t)} --> {ts(t + s['dur'] - 0.3)}", s["vo"], ""]
        md += [f"**{ts(t, '.')[3:8]}** ({s['dur']:.0f} s), on screen: _{s['cap']}_", "", f"> {s['vo']}", ""]
        t += s["dur"]
    (OUT / "CourtroomAI_demo.srt").write_text("\n".join(srt), encoding="utf-8")
    (OUT / "VOICEOVER.md").write_text("\n".join(md), encoding="utf-8")
    print(f"OK: {voiced.relative_to(ROOT)}, {silent.relative_to(ROOT)}, CourtroomAI_demo.srt, VOICEOVER.md")


if __name__ == "__main__":
    main()
