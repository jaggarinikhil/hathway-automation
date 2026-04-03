"""
Hathway STB Renewal — Browser UI Launcher
==========================================
Run this file to open a local browser page where you can enter
box numbers and watch live renewal logs streamed back in real time.

Usage:
    python web_ui.py --config-file config.json
"""

import asyncio
import json
import re
import threading
import time
import queue
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from config import Config

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
log_queue: queue.Queue = queue.Queue()
automation_running = False
automation_done = False
automation_boxes: list = []

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hathway STB Renewal</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: 'Inter', sans-serif;
    background: #0d0d1a;
    color: #e2e8f0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 40px 20px;
  }

  .card {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    border: 1px solid #2d3748;
    border-radius: 20px;
    padding: 40px;
    width: 100%;
    max-width: 700px;
    box-shadow: 0 25px 60px rgba(0,0,0,0.5);
  }

  .logo {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 32px;
  }
  .logo-icon {
    width: 48px; height: 48px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 24px;
  }
  .logo-text h1 { font-size: 22px; font-weight: 700; color: #fff; }
  .logo-text p  { font-size: 13px; color: #718096; margin-top: 2px; }

  label {
    display: block;
    font-size: 13px;
    font-weight: 600;
    color: #a0aec0;
    margin-bottom: 8px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }

  textarea {
    width: 100%;
    height: 160px;
    background: #0d0d1a;
    border: 1.5px solid #2d3748;
    border-radius: 12px;
    color: #e2e8f0;
    font-family: 'Inter', monospace;
    font-size: 14px;
    padding: 16px;
    resize: vertical;
    transition: border-color 0.2s;
    outline: none;
  }
  textarea:focus { border-color: #667eea; }
  textarea::placeholder { color: #4a5568; }

  .hint {
    font-size: 12px;
    color: #4a5568;
    margin-top: 8px;
  }

  .btn {
    margin-top: 24px;
    width: 100%;
    padding: 16px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border: none;
    border-radius: 12px;
    color: #fff;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.2s, transform 0.1s;
    letter-spacing: 0.3px;
  }
  .btn:hover:not(:disabled) { opacity: 0.9; transform: translateY(-1px); }
  .btn:active { transform: translateY(0); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }

  /* Log panel */
  #log-section {
    width: 100%;
    max-width: 700px;
    margin-top: 28px;
    display: none;
  }
  #log-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }
  #log-header span { font-size: 14px; font-weight: 600; color: #a0aec0; }

  .pulse {
    width: 10px; height: 10px;
    border-radius: 50%;
    background: #48bb78;
    animation: pulse 1.4s infinite;
  }
  .pulse.done { background: #ed8936; animation: none; }
  @keyframes pulse {
    0%,100% { opacity: 1; transform: scale(1); }
    50%      { opacity: 0.4; transform: scale(0.8); }
  }

  #log-box {
    background: #0a0a14;
    border: 1px solid #2d3748;
    border-radius: 14px;
    padding: 20px;
    height: 420px;
    overflow-y: auto;
    font-family: 'Courier New', monospace;
    font-size: 12.5px;
    line-height: 1.7;
    scroll-behavior: smooth;
  }

  .log-line { display: block; white-space: pre-wrap; word-break: break-all; }
  .log-INFO    { color: #a0aec0; }
  .log-SUCCESS { color: #68d391; }
  .log-ERROR   { color: #fc8181; }
  .log-WARNING { color: #f6ad55; }
  .log-STEP    { color: #76e4f7; }

  #box-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 16px;
    min-height: 32px;
  }
  .tag {
    background: rgba(102,126,234,0.15);
    border: 1px solid #667eea44;
    border-radius: 8px;
    padding: 4px 12px;
    font-size: 12px;
    color: #a3bffa;
    font-family: monospace;
  }
</style>
</head>
<body>

<div class="card" id="form-card">
  <div class="logo">
    <div class="logo-icon">📺</div>
    <div class="logo-text">
      <h1>Hathway STB Renewal</h1>
      <p>Automated box renewal portal</p>
    </div>
  </div>

  <label for="boxes">Box Numbers</label>
  <textarea id="boxes" placeholder="Paste box numbers here...
e.g.
000115433260
N70934503072
N70934527816

(one per line, or comma/space separated)"></textarea>
  <p class="hint">💡 One per line • or comma/space separated • or all mixed together</p>

  <div id="box-tags"></div>

  <button class="btn" id="start-btn" onclick="startRenewal()">🚀 Start Renewal</button>
</div>

<div id="log-section">
  <div id="log-header">
    <div class="pulse" id="pulse-dot"></div>
    <span id="log-status">Running automation...</span>
  </div>
  <div id="log-box" id="log-box"></div>
</div>

<script>
  const ta = document.getElementById('boxes');
  const tagsEl = document.getElementById('box-tags');

  function parseBoxes(raw) {
    return raw.split(/[\\s,]+/).map(s => s.trim()).filter(Boolean);
  }

  ta.addEventListener('input', () => {
    const boxes = parseBoxes(ta.value);
    tagsEl.innerHTML = boxes.map(b => `<span class="tag">${b}</span>`).join('');
  });

  function startRenewal() {
    const boxes = parseBoxes(ta.value);
    if (boxes.length === 0) {
      ta.style.borderColor = '#fc8181';
      setTimeout(() => ta.style.borderColor = '', 1000);
      return;
    }

    document.getElementById('start-btn').disabled = true;
    document.getElementById('start-btn').textContent = '⏳ Starting...';
    document.getElementById('log-section').style.display = 'block';

    // Submit boxes
    fetch('/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({boxes})
    });

    // Connect to log stream
    const logBox = document.getElementById('log-box');
    const src = new EventSource('/logs');

    src.onmessage = (e) => {
      const data = JSON.parse(e.data);
      if (data.type === 'done') {
        src.close();
        document.getElementById('pulse-dot').classList.add('done');
        document.getElementById('log-status').textContent = 'Automation complete';
        document.getElementById('start-btn').disabled = false;
        document.getElementById('start-btn').textContent = '🔄 Run Again';
        return;
      }
      const line = document.createElement('span');
      line.className = 'log-line log-' + (data.level || 'INFO');
      line.textContent = data.msg;
      logBox.appendChild(line);
      logBox.scrollTop = logBox.scrollHeight;
    };
  }
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Queue-based logger that the automation will write into
# ---------------------------------------------------------------------------
class QueueLogger:
    """Drop-in replacement for LoggerAgent that also pushes to the log_queue."""

    def __init__(self, real_logger, q: queue.Queue):
        self.real = real_logger
        self.q = q

    def _push(self, level: str, msg: str):
        self.q.put({"level": level, "msg": msg})

    def debug(self, msg, **_):
        self.real.debug(msg)
        self._push("INFO", msg)

    def info(self, msg, **_):
        self.real.info(msg)
        self._push("INFO", msg)

    def success(self, msg, **_):
        self.real.success(msg)
        self._push("SUCCESS", msg)

    def error(self, msg, exc_info=False, **_):
        self.real.error(msg, exc_info=exc_info)
        self._push("ERROR", msg)

    def warning(self, msg, **_):
        self.real.warning(msg)
        self._push("WARNING", msg)

    def log_captcha_attempt(self, attempt: int, extracted: str, success: bool):
        self.real.log_captcha_attempt(attempt, extracted, success)
        status = "✅ OK" if success else "❌ FAIL"
        self._push("INFO", f"[CAPTCHA] Attempt {attempt} | Extracted='{extracted}' | {status}")

    def log_login_attempt(self, attempt: int, success: bool):
        self.real.log_login_attempt(attempt, success)
        status = "SUCCESS" if success else "FAILED"
        self._push("INFO" if success else "ERROR", f"[LOGIN] Attempt {attempt} → {status}")

    def log_box_result(self, box_number: str, success: bool, reason: str = ""):
        self.real.log_box_result(box_number, success, reason)
        tag = "✅" if success else "❌"
        msg = f"[BOX {box_number}] {tag} {'SUCCESS' if success else 'FAILED'}"
        if reason:
            msg += f" — {reason}"
        self._push("SUCCESS" if success else "ERROR", msg)

    def log_step(self, box_number: str, step: str, success: bool, detail: str = ""):
        self.real.log_step(box_number, step, success, detail)
        status = "OK" if success else "FAIL"
        self._push("INFO", f"[BOX {box_number}][STEP:{step}] {status} {detail}")

    def get_summary(self):
        return self.real.get_summary()


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # silence default access logs

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._send(200, "text/html; charset=utf-8", HTML_PAGE.encode())

        elif path == "/logs":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            try:
                while True:
                    try:
                        item = log_queue.get(timeout=0.4)
                        if item.get("type") == "done":
                            data = json.dumps(item)
                            self.wfile.write(f"data: {data}\n\n".encode())
                            self.wfile.flush()
                            break
                        data = json.dumps(item)
                        self.wfile.write(f"data: {data}\n\n".encode())
                        self.wfile.flush()
                    except queue.Empty:
                        # heartbeat
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        global automation_running, automation_done, automation_boxes
        path = urlparse(self.path).path

        if path == "/start":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)
            automation_boxes = data.get("boxes", [])

            # Clear the queue
            while not log_queue.empty():
                try:
                    log_queue.get_nowait()
                except queue.Empty:
                    break

            # Run automation in background thread
            t = threading.Thread(target=_run_automation, daemon=True)
            t.start()

            self._send(200, "application/json", b'{"ok":true}')
        else:
            self._send(404, "text/plain", b"Not found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Automation runner (called in a background thread)
# ---------------------------------------------------------------------------
def _run_automation():
    global config_ref
    import asyncio as _asyncio
    from agents.logger_agent import LoggerAgent
    from agents.login_agent import LoginAgent
    from agents.navigation_agent import NavigationAgent
    from agents.renewal_agent import RenewalAgent
    from playwright.async_api import async_playwright

    cfg = config_ref
    cfg.box_numbers = automation_boxes

    async def _run():
        real_logger = LoggerAgent(cfg.log_file)
        logger = QueueLogger(real_logger, log_queue)

        logger.info(f"🚀 Hathway STB Renewal Automation Started")
        logger.info(f"📦 Total boxes to process: {len(cfg.box_numbers)}")

        successful_boxes = []
        failed_boxes = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=cfg.headless,
                slow_mo=cfg.slow_mo,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
            )
            context = await browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            page = await context.new_page()

            try:
                login_agent = LoginAgent(page, cfg, logger)
                login_success = await login_agent.login()
                if not login_success:
                    logger.error("❌ Login failed after all retries. Aborting.")
                    await browser.close()
                    log_queue.put({"type": "done"})
                    return

                logger.success("✅ Login successful")

                nav_agent = NavigationAgent(page, cfg, logger)
                await nav_agent.handle_post_login_slides()

                nav_success = await nav_agent.go_to_package_management()
                if not nav_success:
                    logger.error("❌ Could not navigate to Package Management. Aborting.")
                    await browser.close()
                    log_queue.put({"type": "done"})
                    return

                renewal_agent = RenewalAgent(page, cfg, logger)
                for idx, box_number in enumerate(cfg.box_numbers, 1):
                    logger.info(f"📺 Processing box {idx}/{len(cfg.box_numbers)}: {box_number}")
                    success = await renewal_agent.renew_box(box_number)
                    if success:
                        successful_boxes.append(box_number)
                        logger.success(f"✅ Box {box_number} renewed successfully")
                    else:
                        failed_boxes.append(box_number)
                        logger.error(f"❌ Box {box_number} failed after retries")

                    await _asyncio.sleep(2.0)
                    await page.evaluate("""
                        var btns = document.querySelectorAll('input[type=button],input[type=submit],button');
                        for (var i=0;i<btns.length;i++){
                            var v=(btns[i].value||btns[i].innerText||'').trim().toUpperCase();
                            if(v==='OK'){btns[i].click();break;}
                        }
                    """)
                    await _asyncio.sleep(1.0)
                    await page.evaluate("""
                        var btns=document.querySelectorAll('input[type=button],input[type=submit],button');
                        for(var i=0;i<btns.length;i++){
                            var v=(btns[i].value||btns[i].innerText||'').trim().toUpperCase();
                            if(v==='CANCEL'){var el=btns[i];if(el.offsetParent!==null){el.click();break;}}
                        }
                        var ids=['MasterBody_pnlrenewalPlan','MasterBody_pnlAdd','mpeAdd_backgroundElement'];
                        ids.forEach(function(id){var el=document.getElementById(id);if(el)el.style.display='none';});
                    """)
                    await _asyncio.sleep(1.0)
                    await page.evaluate("""
                        var sb=document.getElementById('MasterBody_txtSearchParam');if(sb)sb.value='';
                    """)
                    await _asyncio.sleep(cfg.delay_between_boxes)

            except Exception as e:
                logger.error(f"💥 Unexpected error: {e}")
            finally:
                await browser.close()
                logger.info("🔒 Browser closed")

        total = len(successful_boxes) + len(failed_boxes)
        logger.info(f"━━━ SUMMARY ━━━  Total: {total}  ✅ Success: {len(successful_boxes)}  ❌ Failed: {len(failed_boxes)}")
        if successful_boxes:
            logger.success("Renewed: " + ", ".join(successful_boxes))
        if failed_boxes:
            logger.error("Failed:  " + ", ".join(failed_boxes))

        log_queue.put({"type": "done"})

    _asyncio.run(_run())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    config_ref = Config.from_args_or_env()

    PORT = 8765
    server = HTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"

    print(f"\n{'='*50}")
    print(f"  🌐  Hathway STB Renewal — Web UI")
    print(f"{'='*50}")
    print(f"  Opening: {url}")
    print(f"  Press Ctrl+C to stop the server")
    print(f"{'='*50}\n")

    # Open browser after a short delay
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped.")
