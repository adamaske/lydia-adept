#!/usr/bin/env python3
"""Browser editor / viewer for make_montage.py montages.

    python editor.py                 # opens http://127.0.0.1:8765 in the browser
    python editor.py --port 9000 --no-browser

Serves editor.html and a tiny JSON API on top of make_montage.py:

    GET  /api/positions          10-10 labels with 3-D scalp coords (cm), 2-D layout coords, normals
    GET  /api/montages           the built-in PianoNoise spec plus every out/<name>/spec.json
    POST /api/build   {spec}     runs build() + all writers exactly like the CLI; returns the summary
    POST /api/preview {spec}     build() only (channels + distances), no files written

Standard library only; the build itself needs whatever make_montage.py needs (numpy, scipy,
matplotlib for the png).
"""
import argparse
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_montage as mm  # noqa: E402

OUT = os.path.join(HERE, "out")


def positions_json():
    pos = mm.load_positions()
    return {l: {"c3": p["c3"].tolist(), "c2": p["c2"].tolist(), "n": p["n"].tolist()} for l, p in pos.items()}


def montages_json():
    specs = [dict(mm.PIANO_NOISE, builtin=True)]
    if os.path.isdir(OUT):
        for name in sorted(os.listdir(OUT)):
            f = os.path.join(OUT, name, "spec.json")
            if os.path.isfile(f) and name != mm.PIANO_NOISE["name"]:
                with open(f) as fh:
                    specs.append(json.load(fh))
    return specs


def summary(m):
    idx = m["index_c"].astype(int)
    return {
        "name": m["name"], "sources": m["sources"], "detectors": m["detectors"],
        "channels": [{"ch": k + 1, "s": int(i), "d": int(j), "mm": round(float(m["dist_mm"][k]), 1)}
                     for k, (i, j) in enumerate(idx)],
    }


def clean_spec(raw):
    spec = dict(mm.PIANO_NOISE)
    spec.update({k: raw[k] for k in ("name", "sources", "detectors", "min_mm", "max_mm", "exclude", "include") if k in raw})
    spec["name"] = "".join(c for c in str(spec["name"]).strip() if c.isalnum() or c in "-_") or "Custom"
    if not spec["sources"] or not spec["detectors"]:
        raise ValueError("place at least one source and one detector")
    return spec


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # quieter than the default
        if self.path.startswith("/api/"):
            sys.stderr.write("%s %s\n" % (self.command, self.path))

    def do_GET(self):
        if self.path in ("/", "/index.html", "/editor.html"):
            with open(os.path.join(HERE, "editor.html"), encoding="utf-8") as f:
                html = f.read().replace("/*BOOT*/null", json.dumps({"positions": positions_json(), "montages": montages_json()}), 1)
            return self._send(200, html.encode("utf-8"), "text/html")
        if self.path == "/api/positions":
            return self._send(200, positions_json())
        if self.path == "/api/montages":
            return self._send(200, montages_json())
        if self.path.startswith("/out/"):
            p = os.path.normpath(os.path.join(HERE, self.path.lstrip("/")))
            if p.startswith(OUT) and os.path.isfile(p):
                with open(p, "rb") as f:
                    return self._send(200, f.read(), "image/png" if p.endswith(".png") else "application/octet-stream")
        self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            raw = json.loads(self.rfile.read(n) or b"{}")
            spec = clean_spec(raw)
        except Exception as e:
            return self._send(400, {"error": str(e)})
        if self.path not in ("/api/build", "/api/preview"):
            return self._send(404, {"error": "not found"})
        try:
            # make_montage uses sys.exit for user errors; turn those into a 400.
            m = mm.build(spec, mm.load_positions())
        except SystemExit as e:
            return self._send(400, {"error": str(e)})
        res = summary(m)
        if self.path == "/api/preview":
            return self._send(200, res)
        try:
            outdir = os.path.join(OUT, m["name"])
            os.makedirs(outdir, exist_ok=True)
            mm.write_probeinfo_mat(m, os.path.join(outdir, "Standard_probeInfo.mat"))
            mm.write_nirsite_txt(m, outdir)
            mm.write_ncfg(m, os.path.join(OUT, m["name"] + ".ncfg"),
                          accelerometer=bool(raw.get("accelerometer", True)), biosignals=bool(raw.get("biosignals", False)))
            mm.write_figure(m, os.path.join(outdir, "montage.png"))
            mm.write_spec(spec, os.path.join(outdir, "spec.json"))
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        res["written"] = {"dir": os.path.relpath(outdir, HERE), "ncfg": os.path.relpath(os.path.join(OUT, m["name"] + ".ncfg"), HERE),
                          "png": f"/out/{m['name']}/montage.png"}
        self._send(200, res)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    a = p.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"montage editor at {url}  (Ctrl-C to stop)")
    if not a.no_browser:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
