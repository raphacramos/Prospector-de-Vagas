"""Cliente HTTP da stdlib com TLS verificado.

A v2 usava ssl._create_unverified_context(). Aqui a verificacao fica ligada; se o
Python do macOS recusar o certificado (certificados nao instalados), cai para o curl,
que usa os certificados do sistema e tambem verifica. Para corrigir o Python de vez, rode
"Install Certificates.command" na pasta do Python em /Applications.
"""
import json
import os
import ssl
import subprocess
import sys
import urllib.error
import urllib.request

DEFAULT_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Prospector/3"


def _is_certificate_error(exc):
    reason = getattr(exc, "reason", exc)
    return isinstance(reason, ssl.SSLError) or "CERTIFICATE" in str(exc).upper()


class UrllibHttpClient:
    def __init__(self, timeout=15, use_curl_fallback=True, debug=None):
        self.timeout = timeout
        self.use_curl_fallback = use_curl_fallback
        self.debug = os.environ.get("PROSPECTOR_DEBUG") == "1" if debug is None else debug
        self.last_error = None
        self._ctx = ssl.create_default_context()

    def _log(self, msg):
        if self.debug:
            print(f"[http] {msg}", file=sys.stderr)

    def _headers(self, url, headers):
        h = {"User-Agent": DEFAULT_UA}
        token = os.environ.get("GITHUB_TOKEN")
        if token and url.startswith("https://api.github.com/"):
            h["Authorization"] = f"Bearer {token}"  # limite de 60 req/h sem token
        h.update(headers or {})
        return h

    def get_text(self, url, headers=None):
        self.last_error = None
        h = self._headers(url, headers)
        req = urllib.request.Request(url, headers=h)
        try:
            with urllib.request.urlopen(req, context=self._ctx, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            self.last_error = f"HTTP {e.code} em {url}"
            self._log(self.last_error)
            return None  # erro do servidor: o curl teria o mesmo resultado
        except Exception as e:  # rede, DNS, certificado
            self.last_error = f"{type(e).__name__}: {e}"
            if not (self.use_curl_fallback and _is_certificate_error(e)):
                self._log(self.last_error)
                return None  # timeout/DNS: o curl falharia igual e dobraria a espera
            self._log(f"certificado recusado pelo Python ({self.last_error}); tentando curl")
        return self._curl(url, h)

    def _curl(self, url, headers):
        cmd = ["curl", "-sS", "-L", "--fail", "--max-time", str(self.timeout)]
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
        cmd.append(url)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout + 5)
        except (OSError, subprocess.SubprocessError) as e:
            self.last_error = f"{self.last_error}; curl indisponivel: {e}"
            return None
        if res.returncode == 0 and res.stdout.strip():
            self.last_error = None
            return res.stdout
        self.last_error = f"{self.last_error}; curl: {res.stderr.strip()[:200]}"
        self._log(self.last_error)
        return None

    def get_json(self, url, headers=None):
        text = self.get_text(url, headers=headers)
        if text is None:
            return None
        try:
            return json.loads(text)
        except ValueError:
            self.last_error = f"resposta nao e JSON em {url}"
            return None


_default = None


def default_client():
    global _default
    if _default is None:
        _default = UrllibHttpClient()
    return _default
