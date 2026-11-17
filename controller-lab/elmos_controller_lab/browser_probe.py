"""Local-only browser Gamepad API probe (no third-party network requests)."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
import webbrowser


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Elmo's Controller Lab — Browser Gamepad Probe</title>
<style>
:root{color-scheme:dark;font:15px/1.5 "Segoe UI",sans-serif;background:#101714;color:#e7eee9}
body{max-width:1000px;margin:32px auto;padding:0 20px}
h1{letter-spacing:.06em;font-size:24px} .muted{color:#9aaca2}
.card{background:#1b2821;border:1px solid #30443a;border-radius:12px;padding:16px;margin:12px 0}
.row{display:flex;gap:12px;flex-wrap:wrap}.pill{background:#2d4739;border-radius:30px;padding:3px 10px}
.axis{display:inline-block;background:#2a3830;border-radius:5px;padding:3px 7px;margin:3px}
button{background:#2d6b4a;color:white;border:0;border-radius:8px;padding:10px 15px}
</style>
</head>
<body>
<h1>ELMO'S CONTROLLER LAB</h1>
<p class="muted">Browser Gamepad API compatibility probe · Localhost only</p>
<div class="card">
  <div id="status">Waiting for browser Gamepad API…</div>
  <p class="muted">Press any button on a controller once to activate browser access. This page only reads gamepad state.</p>
  <button id="refresh">Refresh snapshot</button>
</div>
<div id="devices"></div>
<script>
const statusEl=document.getElementById("status");
const devicesEl=document.getElementById("devices");
let last="";
function snapshot(){
  const pads=Array.from(navigator.getGamepads?navigator.getGamepads():[]).filter(Boolean);
  const devices=pads.map(p=>({
    index:p.index,id:p.id,mapping:p.mapping,connected:p.connected,
    timestamp:p.timestamp,axes:Array.from(p.axes),
    buttons:Array.from(p.buttons).map((b,i)=>({index:i,pressed:b.pressed,value:Number(b.value.toFixed(3))})),
    vibration:!!p.vibrationActuator
  }));
  statusEl.innerHTML='<span class="pill">'+devices.length+' browser-visible controller(s)</span>';
  devicesEl.innerHTML=devices.map(d=>'<div class="card"><h3>'+escapeHtml(d.id)+'</h3>'+
    '<div class="row"><span class="pill">Index '+d.index+'</span><span class="pill">Mapping '+(d.mapping||'raw')+'</span><span class="pill">Vibration '+(d.vibration?'yes':'no')+'</span></div>'+
    '<h4>Axes</h4>'+d.axes.map((v,i)=>'<span class="axis">A'+i+': '+v.toFixed(3)+'</span>').join('')+
    '<h4>Buttons</h4>'+d.buttons.map(b=>'<span class="axis">B'+b.index+': '+(b.pressed?'DOWN':'up')+' ('+b.value+')</span>').join('')+
    '</div>').join('')||'<div class="card muted">No controller is currently visible to this browser.</div>';
  fetch('/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({time:Date.now(),devices})}).catch(()=>{});
}
function escapeHtml(value){return String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
document.getElementById("refresh").addEventListener("click",snapshot);
window.addEventListener("gamepadconnected",snapshot);
window.addEventListener("gamepaddisconnected",snapshot);
snapshot();setInterval(snapshot,250);
</script>
</body></html>"""


class BrowserProbeServer:
    def __init__(self):
        self._lock = threading.Lock()
        self._latest = {"time": 0, "devices": []}
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/" or self.path.startswith("/index"):
                    payload = PAGE.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                elif self.path == "/status":
                    payload = json.dumps(owner.snapshot()).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                else:
                    self.send_error(404)
                    return
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self):
                if self.path != "/report":
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 65536:
                    self.send_error(413)
                    return
                try:
                    report = json.loads(self.rfile.read(length))
                    if not isinstance(report, dict) or not isinstance(report.get("devices"), list):
                        raise ValueError("Invalid report")
                    with owner._lock:
                        owner._latest = {
                            "time": int(report.get("time", 0)),
                            "devices": report["devices"][:16],
                        }
                    self.send_response(204)
                    self.end_headers()
                except Exception:
                    self.send_error(400)

            def log_message(self, *_args):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/"

    def start(self, open_browser: bool = True) -> str:
        self.thread.start()
        if open_browser:
            webbrowser.open(self.url)
        return self.url

    def snapshot(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._latest))

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
