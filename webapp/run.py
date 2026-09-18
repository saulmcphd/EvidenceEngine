"""
Launch the EvidenceEngine local web app.

    python EvidenceEngine/webapp/run.py

Builds the interface once (needs Node only the first time / after a UI change), then starts a local server
at http://127.0.0.1:8000 and opens your browser. Everything runs on your machine; nothing is uploaded.
"""
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "frontend" / "dist"
PORT = 8000


def ensure_build():
    if DIST.exists():
        return
    print("Building the interface (one-time)…")
    npm = "npm.cmd" if sys.platform.startswith("win") else "npm"
    subprocess.run([npm, "install"], cwd=str(HERE / "frontend"), check=True)
    subprocess.run([npm, "run", "build"], cwd=str(HERE / "frontend"), check=True)


def main():
    ensure_build()
    sys.path.insert(0, str(HERE))
    import uvicorn
    from backend.app import app
    threading.Timer(1.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    print(f"EvidenceEngine running at http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
