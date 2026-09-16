"""Gera PDF a partir de HTML com Chrome/Chromium headless."""
import os
import shutil
import subprocess
import tempfile
import time

MAC_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]
PATH_CANDIDATES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"]


class PdfRendererUnavailable(Exception):
    pass


def find_chrome(configured=""):
    for candidate in [configured, os.environ.get("CHROME_PATH", "")]:
        if candidate:
            if os.path.exists(candidate):
                return candidate
            raise PdfRendererUnavailable(f"Chrome configurado não existe: {candidate}")
    for candidate in MAC_CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    for name in PATH_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    raise PdfRendererUnavailable(
        "Chrome/Chromium não encontrado. Defina 'chrome_path' no perfil ou a variável CHROME_PATH.")


class ChromePdfRenderer:
    def __init__(self, chrome_path=""):
        self.configured = chrome_path

    def render(self, html_path, pdf_path, timeout=30):
        chrome = find_chrome(self.configured)
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        user_dir = tempfile.mkdtemp(prefix="prospector-chrome-")
        cmd = [
            chrome, "--headless", "--disable-gpu", "--disable-background-networking",
            "--disable-extensions", "--disable-sync", "--no-first-run", "--no-default-browser-check",
            "--no-pdf-header-footer", f"--user-data-dir={user_dir}", f"--print-to-pdf={pdf_path}",
            "file://" + os.path.abspath(html_path),
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + timeout
            last_size = -1
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    break
                size = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else -1
                if size > 0 and size == last_size:
                    break  # algumas versoes do Chrome nao encerram sozinhas apos gerar o PDF
                last_size = size
                time.sleep(0.5)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
            shutil.rmtree(user_dir, ignore_errors=True)
        return os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0
