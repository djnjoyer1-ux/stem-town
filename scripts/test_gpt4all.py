import json
import urllib.request

BASE = "http://127.0.0.1:4891/v1"

def get(url):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)

print("Testing GPT4All at", BASE)
models = get(BASE + "/models").get("data", [])
if not models:
    raise SystemExit("GPT4All responded, but no models were returned.")

print("Models:", ", ".join(m.get("id", "?") for m in models))
print("SUCCESS")
