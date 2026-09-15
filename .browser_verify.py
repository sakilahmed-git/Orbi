import base64
import json
import time
from pathlib import Path

import requests
import websocket


OUT = Path("demo/screenshots")
BASE = "http://127.0.0.1:3000"
sequence = 0


def new_page():
    info = requests.put(f"http://127.0.0.1:9223/json/new?{BASE}").json()
    return websocket.create_connection(info["webSocketDebuggerUrl"], origin="http://localhost:9222")


ws = new_page()


def cdp(method, params=None):
    global sequence
    sequence += 1
    ws.send(json.dumps({"id": sequence, "method": method, "params": params or {}}))
    while True:
        message = json.loads(ws.recv())
        if message.get("id") == sequence:
            if "error" in message:
                raise RuntimeError(message["error"])
            return message.get("result", {})


def js(expression):
    return cdp("Runtime.evaluate", {"expression": expression, "returnByValue": True})["result"].get("value")


def open_route(route, width, height):
    cdp("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})
    cdp("Page.navigate", {"url": BASE + route})
    for _ in range(100):
        if js("document.readyState") == "complete":
            break
        time.sleep(0.1)
    time.sleep(1)


def shot(name):
    png = cdp("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})["data"]
    (OUT / name).write_bytes(base64.b64decode(png))


def set_scenario(freq, amp, noise, seed):
    expression = f"""
    (() => {{
      const values = [{freq}, {amp}, {noise}, {seed}];
      const inputs = [...document.querySelectorAll('input[type=number]')];
      inputs.forEach((input, index) => {{
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(input, String(values[index]));
        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
      }});
      [...document.querySelectorAll('button')].find(button => button.textContent.includes('Run scenario')).click();
    }})()
    """
    js(expression)


def wait_complete(timeout=25):
    for _ in range(timeout * 5):
        text = js("document.body.innerText") or ""
        if "complete" in text and "Disturbance-armed outcome" in text:
            return text
        time.sleep(0.2)
    raise TimeoutError("scenario did not complete")


cdp("Page.enable")
cdp("Runtime.enable")
cdp("Page.addScriptToEvaluateOnNewDocument", {"source": """
  window.__scintillaDraws = [];
  const original = CanvasRenderingContext2D.prototype.fillRect;
  CanvasRenderingContext2D.prototype.fillRect = function(x, y, width, height) {
    if (this.canvas && this.canvas.width === 256 && x === 0 && y === 0 && width === 256 && height === 256) {
      window.__scintillaDraws.push(performance.now());
    }
    return original.apply(this, arguments);
  };
"""})

open_route("/", 1440, 1000)
shot("overview-desktop.png")
open_route("/", 390, 844)
shot("overview-mobile.png")

open_route("/envelope", 1440, 1000)
time.sleep(2)
shot("envelope-desktop.png")
open_route("/envelope", 390, 844)
time.sleep(2)
shot("envelope-mobile.png")

open_route("/demo", 1440, 1000)
set_scenario(17.3, 3.0, 5.0, 812)
demo_text = wait_complete()
draws = js("window.__scintillaDraws") or []
shot("demo-desktop.png")

scenario_results = []
for scenario in [(12.0, 2.0, 1.0, 42), (24.0, 4.5, 6.0, 987)]:
    set_scenario(*scenario)
    scenario_results.append({"scenario": scenario, "text": wait_complete()})

open_route("/demo", 390, 844)
set_scenario(17.3, 3.0, 5.0, 812)
wait_complete()
shot("demo-mobile.png")

result = {
    "default_text": demo_text,
    "scenarios": scenario_results,
    "draw_count": len(draws),
    "draw_first_ms": draws[0] if draws else None,
    "draw_last_ms": draws[-1] if draws else None,
    "max_draw_gap_ms": max([b - a for a, b in zip(draws, draws[1:])], default=None),
    "screenshot_files": sorted(path.name for path in OUT.glob("*.png")),
}
Path("demo/screenshots/verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
ws.close()
