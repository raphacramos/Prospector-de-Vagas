"""Servidor do painel: so escuta em 127.0.0.1 e exige o token da sessao em toda chamada."""
import json
import mimetypes
import os
import re
import secrets
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from prospector.domain.lead import LeadStatus
from prospector.ports import LlmError, MiningOptions
from prospector.services.application import ApplicationError
from prospector.services.funnel import funnel_stats
from prospector.services.ranking import match_score, queue_key

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
ALLOWED_FILES = {"cv.pdf", "cv.html", "carta.txt", "carta.pdf", "vaga.txt"}
KNOWN_ERRORS = (ApplicationError, LlmError, ValueError)


class JobRunner:
    """Tarefas demoradas (IA, mineracao, navegador) com consulta de progresso."""

    def __init__(self, workers=3):
        self._pool = ThreadPoolExecutor(max_workers=workers)
        self._jobs = {}
        self._lock = threading.Lock()

    def start(self, kind, fn, *args, lead_id=None):
        job_id = uuid.uuid4().hex[:10]
        with self._lock:
            self._jobs[job_id] = {"id": job_id, "kind": kind, "lead_id": lead_id, "state": "running",
                                  "started": time.time(), "result": None, "error": None}
        self._pool.submit(self._run, job_id, fn, args)
        return self.get(job_id)

    def _run(self, job_id, fn, args):
        try:
            result = fn(*args)
            update = {"state": "done", "result": result}
        except KNOWN_ERRORS as e:
            update = {"state": "error", "error": str(e)}
        except Exception as e:  # erro inesperado: mostra no painel em vez de sumir
            update = {"state": "error", "error": f"{type(e).__name__}: {e}"}
        with self._lock:
            self._jobs[job_id].update(update, finished=time.time())

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def active(self):
        with self._lock:
            return [dict(j) for j in self._jobs.values() if j["state"] == "running"]


def lead_json(lead, score=None, pkg=None):
    return {
        "id": lead.id, "company": lead.company, "title": lead.title, "source": lead.source,
        "url": lead.url, "region": lead.region.value, "status": lead.status.value,
        "location": lead.location, "posted_at": lead.posted_at, "emails": lead.emails,
        "ats_links": lead.ats_links, "labels": lead.labels, "score": score,
        "created_at": lead.created_at, "contacted_at": lead.contacted_at,
        "package": pkg.to_dict() if pkg else None,
    }


class PanelApp:
    """Regras HTTP do painel, separadas do handler para facilitar testes."""

    def __init__(self, container, token=None, jobs=None):
        self.c = container
        self.token = token or secrets.token_urlsafe(18)
        self.jobs = jobs or JobRunner()

    # ------------------------------------------------------------ consultas
    def state(self):
        c = self.c
        counts = {}
        for row in c.repo.funnel_rows():
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        return {
            "name": c.profile.nome, "profile_path": c.profile.path,
            "resume_loaded": c.resume_store.exists, "resume_path": c.resume_store.path,
            "llm_configured": c.llm.configured, "model": c.llm.model,
            "autofill": bool(c.autofill_worker), "counts": counts,
            "statuses": LeadStatus.values(), "sources": list(c.miners),
            "active_jobs": self.jobs.active(),
        }

    def proven_skills(self):
        try:
            return self.c.resume_store.load().known_skills() if self.c.resume_store.exists else set()
        except Exception:
            return set()

    def queue(self, status=None, q="", limit=200):
        leads = self.c.repo.list_recent(limit=2000, status=status or None)
        if q:
            ql = q.lower()
            leads = [l for l in leads if ql in f"{l.company} {l.title} {l.location} {l.source}".lower()]
        proven = self.proven_skills()
        scored = [(l, match_score(l, proven) if proven else None) for l in leads]
        scored.sort(key=lambda pair: queue_key(*pair))
        return [lead_json(l, s, self.c.applications.load(l.id)) for l, s in scored[:limit]]

    def lead(self, lead_id):
        lead = self.c.repo.get(lead_id)
        if not lead:
            return None
        proven = self.proven_skills()
        data = lead_json(lead, match_score(lead, proven) if proven else None, self.c.applications.load(lead_id))
        data["events"] = self.c.repo.events(lead_id)
        data["raw_body"] = lead.raw_body[:6000]
        return data

    def stats(self):
        per_source, total = funnel_stats(self.c.repo.funnel_rows())
        row = lambda s: {"source": s.source, "leads": s.leads, "contacted": s.contacted,
                         "replied": s.replied, "rate": s.reply_rate, "discarded": s.discarded}
        return {"sources": [row(s) for s in per_source], "total": row(total)}

    # ---------------------------------------------------------------- acoes
    def prepare(self, lead_id, language=None):
        def run():
            return self.c.applications.prepare(lead_id, language=language or None).to_dict()
        return self.jobs.start("prepare", run, lead_id=lead_id)

    def apply(self, lead_id):
        def run():
            mode, payload = self.c.apply_flow.start(lead_id)
            if mode == "autofill":
                return {"mode": mode, "report": payload.result(timeout=240).to_dict()}
            return {"mode": mode, **payload}
        return self.jobs.start("apply", run, lead_id=lead_id)

    def mine(self, body):
        names = [body["source"]] if body.get("source") not in (None, "", "all") else list(self.c.miners)
        options = MiningOptions(query=body.get("query") or None, remote_only=bool(body.get("remote_only")),
                                all_levels=bool(body.get("all_levels")), limit=int(body.get("limit") or 30))

        def run():
            report = self.c.mining.run(names, options)
            return {"inserted": report.inserted, "duplicates": report.duplicates,
                    "sources": {k: {"found": v.found, "error": v.error, "warnings": v.warnings}
                                for k, v in report.sources.items()}}
        return self.jobs.start("mine", run)

    def set_status(self, lead_id, status, note=""):
        LeadStatus(status)
        if not self.c.repo.set_status(lead_id, status, note=note or "painel"):
            raise ValueError(f"lead #{lead_id} não encontrado")
        return self.lead(lead_id)

    def file_path(self, lead_id, name):
        if name not in ALLOWED_FILES:
            return None
        pkg = self.c.applications.load(lead_id)
        if not pkg:
            return None
        path = pkg.cv_pdf if name == "cv.pdf" else os.path.join(pkg.folder, name)
        return path if path and os.path.exists(path) else None


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Prospector"

        def log_message(self, fmt, *args):  # silencioso; erros aparecem no painel
            pass

        # --------------------------------------------------------- utilidades
        def _host_ok(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def _token_ok(self, query):
            given = self.headers.get("X-Prospector-Token") or (query.get("token") or [""])[0]
            return secrets.compare_digest(given, app.token)

        def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _error(self, status, message):
            self._send(status, {"error": message})

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > 1_000_000:
                raise ValueError("requisição grande demais")
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw.decode("utf-8") or "{}")

        def _guard(self):
            url = urlparse(self.path)
            query = parse_qs(url.query)
            if not self._host_ok():
                self._error(HTTPStatus.FORBIDDEN, "host não permitido")
                return None
            if not self._token_ok(query):
                self._error(HTTPStatus.UNAUTHORIZED, "token inválido; abra o link mostrado no terminal")
                return None
            return url, query

        # ---------------------------------------------------------------- GET
        def do_GET(self):
            parsed = self._guard()
            if not parsed:
                return
            url, query = parsed
            path = url.path
            try:
                if path in ("/", "/index.html"):
                    with open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8") as f:
                        html = f.read().replace("__TOKEN__", app.token)
                    return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8",
                                      {"Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; script-src 'self' 'unsafe-inline'; frame-src 'self'; img-src 'self' data:"})
                if path == "/api/state":
                    return self._send(200, app.state())
                if path == "/api/queue":
                    return self._send(200, app.queue(status=(query.get("status") or [""])[0],
                                                      q=(query.get("q") or [""])[0]))
                if path == "/api/stats":
                    return self._send(200, app.stats())
                m = re.fullmatch(r"/api/leads/(\d+)", path)
                if m:
                    data = app.lead(int(m.group(1)))
                    return self._send(200, data) if data else self._error(404, "lead não encontrado")
                m = re.fullmatch(r"/api/jobs/([0-9a-f]+)", path)
                if m:
                    job = app.jobs.get(m.group(1))
                    return self._send(200, job) if job else self._error(404, "tarefa não encontrada")
                m = re.fullmatch(r"/files/(\d+)/([a-z.]+)", path)
                if m:
                    fpath = app.file_path(int(m.group(1)), m.group(2))
                    if not fpath:
                        return self._error(404, "arquivo não encontrado")
                    ctype = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
                    if ctype.startswith("text/"):
                        ctype += "; charset=utf-8"
                    with open(fpath, "rb") as f:
                        return self._send(200, f.read(), ctype)
                return self._error(404, "rota não encontrada")
            except Exception as e:
                return self._error(500, f"{type(e).__name__}: {e}")

        # --------------------------------------------------------------- POST
        def do_POST(self):
            parsed = self._guard()
            if not parsed:
                return
            url, _ = parsed
            path = url.path
            try:
                body = self._body()
                m = re.fullmatch(r"/api/leads/(\d+)/(prepare|apply|status|cover-letter)", path)
                if m:
                    lead_id, action = int(m.group(1)), m.group(2)
                    if action == "prepare":
                        return self._send(202, app.prepare(lead_id, body.get("language")))
                    if action == "apply":
                        return self._send(202, app.apply(lead_id))
                    if action == "status":
                        return self._send(200, app.set_status(lead_id, body.get("status", ""), body.get("note", "")))
                    pkg = app.c.applications.update_cover_letter(lead_id, body.get("text", ""))
                    return self._send(200, pkg.to_dict())
                if path == "/api/prepare-batch":
                    ids = [int(i) for i in body.get("ids", [])][:25]
                    return self._send(202, {"jobs": [app.prepare(i, body.get("language")) for i in ids]})
                if path == "/api/mine":
                    return self._send(202, app.mine(body))
                return self._error(404, "rota não encontrada")
            except KNOWN_ERRORS as e:
                return self._error(400, str(e))
            except Exception as e:
                return self._error(500, f"{type(e).__name__}: {e}")

    return Handler


def serve(container, host="127.0.0.1", port=8765, token=None):
    app = PanelApp(container, token=token)
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    return app, httpd
