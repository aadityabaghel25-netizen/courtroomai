"""
Record the real CourtroomAI app for the demo video by driving headless Chrome over the
DevTools protocol. Captures JPEG frames with timestamps into video/frames/<segment>/.
Also renders the title cards (video/slides.html) and the downloaded PDF report.

Needs: the API on :8000 and the Vite dev server on :5173 (both local), Google Chrome.
Usage: python video/record.py
"""

import base64
import json
import shutil
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import websocket  # websocket-client

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "video" / "frames"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
APP = "http://localhost:5173"
PORT = 9333
W, H, SCALE = 1280, 720, 1.5   # 1920x1080 output
FPS = 6


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, max_size=None, timeout=120)
        self.i = 0
        self.lock = threading.Lock()

    def send(self, method, **params):
        with self.lock:
            self.i += 1
            mid = self.i
            self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
            while True:
                msg = json.loads(self.ws.recv())
                if msg.get("id") == mid:
                    if "error" in msg:
                        raise RuntimeError(f"{method}: {msg['error']}")
                    return msg.get("result", {})

    def js(self, expr, await_promise=True):
        r = self.send("Runtime.evaluate", expression=expr, awaitPromise=await_promise, returnByValue=True)
        if r.get("exceptionDetails"):
            raise RuntimeError(f"JS error: {r['exceptionDetails'].get('text')} in {expr[:120]}")
        return r.get("result", {}).get("value")


class Recorder:
    """Background frame grabber. Segments are named folders of numbered JPEGs + times.json."""

    def __init__(self, cdp):
        self.cdp, self.seg, self.frames, self.t0 = cdp, None, [], 0
        self.stop_evt = threading.Event()
        self.thread = None

    def start(self, name):
        self.seg = OUT / name
        shutil.rmtree(self.seg, ignore_errors=True)
        self.seg.mkdir(parents=True)
        self.frames, self.t0 = [], time.time()
        self.stop_evt.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.stop_evt.is_set():
            t = time.time()
            try:
                data = self.cdp.send("Page.captureScreenshot", format="jpeg", quality=88)["data"]
                p = self.seg / f"{len(self.frames):05d}.jpg"
                p.write_bytes(base64.b64decode(data))
                self.frames.append(round(t - self.t0, 3))
            except Exception as e:  # keep recording; log once
                print("frame error:", e)
            time.sleep(max(0, 1 / FPS - (time.time() - t)))

    def stop(self):
        self.stop_evt.set()
        self.thread.join()
        (self.seg / "times.json").write_text(json.dumps(self.frames))
        print(f"  segment {self.seg.name}: {len(self.frames)} frames, {self.frames[-1] if self.frames else 0}s")


CURSOR_JS = """
(() => {
  if (document.getElementById('__cursor')) return;
  const c = document.createElement('div');
  c.id = '__cursor';
  c.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24"><path d="M4 2l7 19 2.5-7.5L21 11z" fill="#141821" stroke="#fff" stroke-width="1.5"/></svg>';
  Object.assign(c.style, {position:'fixed', left:'640px', top:'360px', zIndex: 99999, pointerEvents:'none', transition:'left .6s ease, top .6s ease'});
  document.body.appendChild(c);
})()
"""


def chrome():
    prof = Path("/tmp/claude-501/chrome-video-profile")
    shutil.rmtree(prof, ignore_errors=True)
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={prof}",
                             "--hide-scrollbars", "--no-first-run", "--no-default-browser-check", f"--window-size={W},{H}"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?about:blank", method="PUT")
            target = json.loads(urllib.request.urlopen(req, timeout=2).read())
            return proc, target["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Chrome did not start")


class App:
    def __init__(self, cdp):
        self.c = cdp

    def go(self, url, wait=2.0):
        self.c.send("Page.navigate", url=url)
        time.sleep(wait)
        self.c.js(CURSOR_JS)

    def center(self, js_selector_expr):
        r = self.c.js(f"(() => {{ const e = {js_selector_expr}; if (!e) return null; e.scrollIntoView({{block:'center', behavior:'smooth'}}); return true; }})()")
        if not r:
            raise RuntimeError(f"element not found: {js_selector_expr}")
        time.sleep(0.9)
        return self.c.js(f"(() => {{ const r = ({js_selector_expr}).getBoundingClientRect(); return [r.left + r.width/2, r.top + r.height/2]; }})()")

    def move(self, x, y, pause=0.7):
        self.c.js(f"(() => {{ const c = document.getElementById('__cursor'); if (c) {{ c.style.left = '{x}px'; c.style.top = '{y}px'; }} }})()")
        self.c.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        time.sleep(pause)

    def click(self, js_selector_expr, pause=0.8):
        x, y = self.center(js_selector_expr)
        self.move(x, y)
        for t in ("mousePressed", "mouseReleased"):
            self.c.send("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", clickCount=1)
        time.sleep(pause)

    def hover(self, js_selector_expr, pause=1.6):
        x, y = self.center(js_selector_expr)
        self.move(x, y, pause)

    def scroll_by(self, dy, steps=12, pause=0.08):
        for _ in range(steps):
            self.c.js(f"window.scrollBy(0, {dy / steps})")
            time.sleep(pause)

    def wait_for(self, js_condition, timeout=240):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.c.js(js_condition):
                return True
            time.sleep(1)
        raise RuntimeError(f"timed out waiting for {js_condition}")


def by_text(tag, text):
    return f"[...document.querySelectorAll('{tag}')].find(e => e.textContent.trim().startsWith({json.dumps(text)}))"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    proc, ws = chrome()
    c = CDP(ws)
    try:
        c.send("Page.enable")
        c.send("Runtime.enable")
        c.send("Emulation.setDeviceMetricsOverride", width=W, height=H, deviceScaleFactor=SCALE, mobile=False)
        dl = ROOT / "video" / "downloads"
        shutil.rmtree(dl, ignore_errors=True)
        dl.mkdir(parents=True)
        c.send("Browser.setDownloadBehavior", behavior="allow", downloadPath=str(dl))
        app, rec = App(c), Recorder(c)

        # Title cards
        slides = (ROOT / "video" / "slides.html").as_uri()
        for n in range(1, 7):
            app.go(f"{slides}#s{n}", wait=1.5)
            c.js("document.getElementById('__cursor')?.remove()")
            (OUT / f"slide{n}.jpg").write_bytes(base64.b64decode(
                c.send("Page.captureScreenshot", format="jpeg", quality=92)["data"]))
        print("  slides rendered")

        # Home page
        app.go(APP + "/", wait=3)
        rec.start("home")
        time.sleep(3.5)
        app.hover(by_text("a", "Prepare a case brief"), pause=1.2)
        app.scroll_by(520, steps=20)
        time.sleep(1.2)
        app.scroll_by(-520, steps=10)
        rec.stop()

        # Brief mode
        app.go(APP + "/brief", wait=3)
        rec.start("brief_input")
        time.sleep(1)
        app.click(by_text("button", "Dowry harassment"))
        app.click(by_text("button", "Defence"))
        time.sleep(0.8)
        rec.stop()
        rec.start("brief_pipeline")
        app.click(by_text("button", "Prepare brief"), pause=0.2)
        app.wait_for("!!document.querySelector('h2') && [...document.querySelectorAll('h2')].some(h => h.textContent.includes('Left out') || h.textContent.includes('Supporting judgments'))", timeout=300)
        time.sleep(1.5)
        rec.stop()
        rec.start("brief_result")
        c.js("window.scrollTo({top: 0, behavior: 'smooth'})")
        time.sleep(1.5)
        app.hover("document.querySelector('mark')", pause=2.2)
        app.hover("[...document.querySelectorAll('article')].find(a => a.id && a.id.startsWith('claim-M'))", pause=2.2)
        app.hover("[...document.querySelectorAll('article')].find(a => a.textContent.includes('What the judgment says'))", pause=3.0)
        app.scroll_by(500, steps=25, pause=0.1)
        time.sleep(1.5)
        app.scroll_by(500, steps=25, pause=0.1)
        time.sleep(1.5)
        try:
            app.click(by_text("button", "Left out of the brief"), pause=2.5)
        except RuntimeError:
            pass
        app.scroll_by(400, steps=20, pause=0.1)
        time.sleep(1.5)
        c.js("window.scrollTo({top: 0, behavior: 'smooth'})")
        time.sleep(1.2)
        app.click(by_text("button", "Download PDF report"), pause=3)
        rec.stop()

        # Audit mode
        app.go(APP + "/audit", wait=3)
        rec.start("audit_input")
        app.click(by_text("button", "Load an example"), pause=1.5)
        rec.stop()
        rec.start("audit_pipeline")
        app.click(by_text("button", "Check citations"), pause=0.2)
        app.wait_for("document.querySelectorAll('article').length >= 3", timeout=300)
        time.sleep(2)
        rec.stop()
        rec.start("audit_result")
        c.js("window.scrollTo({top: 0, behavior: 'smooth'})")
        time.sleep(1.5)
        for k in range(4):
            try:
                app.hover(f"document.querySelectorAll('article')[{k}]", pause=2.6)
            except RuntimeError:
                break
        rec.stop()
    finally:
        try:
            c.ws.close()
        finally:
            proc.terminate()

    # PDF pages
    pdfs = sorted((ROOT / "video" / "downloads").glob("*.pdf"))
    if pdfs:
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(str(pdfs[-1]))
        for i in range(min(2, len(doc))):
            doc[i].render(scale=2.2).to_pil().save(OUT / f"pdf{i + 1}.png")
        print(f"  PDF rendered: {pdfs[-1].name}, {len(doc)} pages")
    else:
        print("  WARNING: no PDF downloaded")


if __name__ == "__main__":
    main()
