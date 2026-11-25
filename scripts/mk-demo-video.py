import json, sys, time, urllib.request
def call(p, body=None, tok=None, m="POST", timeout=900):
    req = urllib.request.Request("http://127.0.0.1:8000"+p,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type":"application/json", **({"Authorization":"Bearer "+tok} if tok else {})}, method=m)
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.loads(r.read().decode())
t = call("/api/auth/login", {"email":"instructor@edusense.local","password":"Password123"})["access_token"]
t0 = time.time()
v = call("/api/ai/videos", {"title":"Introduction to Neural Networks",
    "prompt":"Explain neurons, layers, activation functions and backpropagation for beginners",
    "language":"English","style":"Friendly","duration":60,"session_id":3}, t)
print("SECONDS %.1f" % (time.time()-t0))
print("VIDEO id=%s status=%s url=%s scenes=%d" % (v.get("id"), v.get("status"), v.get("video_url"), len((v.get("lesson") or {}).get("sections") or [])))
print(json.dumps({k: v.get(k) for k in ("warnings","script","scenes")}, ensure_ascii=False)[:600])
