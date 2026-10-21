"""اجرای داشبورد.

    python run.py            → http://127.0.0.1:8000
    python run.py --port 8080

برای اتصال به Ollama روی رایانهٔ دیگر:
    set OLLAMA_HOST=http://192.168.1.10:11434   (ویندوز)
    export OLLAMA_HOST=http://192.168.1.10:11434 (لینوکس/مک)
"""
import argparse
import os
import uvicorn

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    print(f"داشبورد: http://127.0.0.1:{a.port}")
    print(f"Ollama : {os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')}")
    uvicorn.run("app.main:app", host=a.host, port=a.port, log_level="info")
