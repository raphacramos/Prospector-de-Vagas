import re
import html
import json
import ssl
import subprocess
import tempfile
import os
import time
import urllib.request

def clean_html(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def fetch_json(url, headers=None, timeout=10):
    text = fetch_text(url, headers=headers, timeout=timeout)
    if text:
        try:
            return json.loads(text)
        except Exception:
            return None
    return None

def fetch_text(url, headers=None, timeout=15):
    if headers is None:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        try:
            cmd = ["curl", "-s", "-L", "-H", f"User-Agent: {headers.get('User-Agent', '')}", url]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout
        except Exception:
            pass
        return None

def compile_html_to_pdf(html_path, pdf_path, timeout=20):
    """Compila arquivo HTML para PDF via Google Chrome headless de alta performance."""
    user_dir = tempfile.mkdtemp()
    if os.path.exists(pdf_path):
        try:
            os.remove(pdf_path)
        except Exception:
            pass
    cmd = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--headless",
        "--disable-gpu",
        "--disable-background-networking",
        "--disable-extensions",
        "--disable-sync",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-pdf-header-footer",
        f"--user-data-dir={user_dir}",
        f"--print-to-pdf={pdf_path}",
        f"file://{html_path}"
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    success = False
    start_time = time.time()
    while time.time() - start_time < timeout:
        time.sleep(0.4)
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 10000:
            time.sleep(0.4)
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
            subprocess.run(["rm", "-rf", user_dir])
            success = True
            break

    if not success:
        proc.kill()
        subprocess.run(["rm", "-rf", user_dir])

    return success and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0
