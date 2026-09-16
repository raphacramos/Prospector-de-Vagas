import re

from prospector.adapters.http import default_client
import html
import subprocess
import tempfile
import os
import time

def clean_html(text):
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def fetch_json(url, headers=None, timeout=10):
    return default_client().get_json(url, headers=headers)


def fetch_text(url, headers=None, timeout=15):
    return default_client().get_text(url, headers=headers)


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
