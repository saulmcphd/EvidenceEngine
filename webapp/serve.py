"""Serve the built EvidenceEngine web app without opening a browser (used by the preview harness / headless).
    python EvidenceEngine/webapp/serve.py [port]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uvicorn
from backend.app import app

if __name__ == "__main__":
    # Port precedence: explicit CLI arg > PORT env (used by the preview harness / autoPort) > 5180 default.
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT") or 5180)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
