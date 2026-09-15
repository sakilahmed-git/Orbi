import json
import requests
import websocket

pages = requests.get("http://127.0.0.1:9223/json").json()
page = next(item for item in pages if item.get("type") == "page" and item.get("url", "").endswith("/demo"))
ws = websocket.create_connection(page["webSocketDebuggerUrl"], origin="http://localhost:9222")
ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": "document.body.innerText", "returnByValue": True}}))
while True:
    message = json.loads(ws.recv())
    if message.get("id") == 1:
        print(message["result"]["result"].get("value"))
        break
ws.close()
