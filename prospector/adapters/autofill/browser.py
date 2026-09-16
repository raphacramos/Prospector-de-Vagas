"""Abre o formulario no Chrome, preenche o que for seguro e deixa o envio com voce.

Playwright e opcional: `pip3 install playwright` (usa o Chrome ja instalado, sem baixar
navegador). Todo uso do Playwright acontece numa unica thread (AutofillWorker).
"""
import os
import queue
import threading
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import List

from prospector.adapters.autofill.fields import (
    FormField, application_url, detect_ats, plan_fields,
)

SCAN_JS = r"""
() => {
  const visible = el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return (r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none') || el.type === 'file';
  };
  const text = el => (el ? (el.innerText || el.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const labelOf = el => {
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l && text(l)) return text(l);
    }
    if (el.getAttribute('aria-labelledby')) {
      const t = el.getAttribute('aria-labelledby').split(/\s+/).map(i => text(document.getElementById(i))).join(' ');
      if (t.trim()) return t.trim();
    }
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
    const wrap = el.closest('label');
    if (wrap && text(wrap)) return text(wrap);
    let node = el.closest('.field, .application-question, .ashby-application-form-field-entry, [class*="field"], li, fieldset, div');
    for (let i = 0; node && i < 3; i++, node = node.parentElement) {
      const l = node.querySelector('label, legend, .application-label, [class*="label"]');
      if (l && text(l)) return text(l);
    }
    return el.placeholder || el.name || '';
  };
  const out = [];
  let n = 0;
  const seenGroups = new Set();
  document.querySelectorAll('input, textarea, select').forEach(el => {
    const type = (el.type || '').toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset'].includes(type)) return;
    if (!visible(el) || el.disabled) return;
    if ((type === 'radio' || type === 'checkbox') && el.name) {
      if (seenGroups.has(el.name)) return;
      seenGroups.add(el.name);
    }
    const pid = 'p' + (n++);
    el.setAttribute('data-prospector-id', pid);
    const group = el.closest('fieldset');
    let label = labelOf(el);
    if ((type === 'radio' || type === 'checkbox') && group) {
      const legend = group.querySelector('legend');
      if (legend) label = text(legend);
    }
    const required = el.required || el.getAttribute('aria-required') === 'true' || /\*\s*$/.test(label);
    const hasValue = type === 'file' ? el.files.length > 0
      : (type === 'radio' || type === 'checkbox') ? !!document.querySelector(`input[name="${CSS.escape(el.name)}"]:checked`)
      : !!(el.value && el.value.trim());
    out.push({
      pid, tag: el.tagName.toLowerCase(), type, label: label.slice(0, 300), name: el.name || el.id || '',
      required, has_value: hasValue,
      options: el.tagName === 'SELECT' ? Array.from(el.options).map(o => o.text.trim()).slice(0, 30) : [],
    });
  });
  return out;
}
"""

MARK_JS = r"""
([filled, manual, total]) => {
  const paint = (ids, color) => ids.forEach(id => {
    const el = document.querySelector(`[data-prospector-id="${id}"]`);
    if (el) { el.style.outline = `2px solid ${color}`; el.style.outlineOffset = '2px'; }
  });
  paint(filled, '#1f9d7a');
  paint(manual, '#e0781f');
  let bar = document.getElementById('prospector-bar');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'prospector-bar';
    bar.style.cssText = 'position:fixed;left:12px;right:12px;bottom:12px;z-index:2147483647;padding:10px 14px;' +
      'border-radius:8px;background:#10231e;color:#e8f3ef;font:14px/1.4 system-ui,sans-serif;' +
      'box-shadow:0 6px 24px rgba(0,0,0,.25)';
    document.body.appendChild(bar);
  }
  bar.textContent = `Prospector: ${filled.length} de ${total} campos preenchidos (verde). ` +
    (manual.length ? `${manual.length} precisam de você (laranja). ` : '') +
    'Revise tudo e clique em enviar. Depois marque como enviada no painel.';
}
"""


class AutofillUnavailable(Exception):
    pass


@dataclass
class AutofillReport:
    lead_id: int
    url: str
    ats: str
    filled: List[str] = field(default_factory=list)       # rotulos preenchidos
    uploaded: List[str] = field(default_factory=list)
    answered: List[str] = field(default_factory=list)     # perguntas respondidas pela IA
    manual: List[str] = field(default_factory=list)       # rotulos para voce
    errors: List[str] = field(default_factory=list)

    def to_dict(self):
        return dict(self.__dict__)


def playwright_available():
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False


class BrowserSession:
    """Mantem um Chrome aberto com perfil proprio (logins em ATS ficam salvos)."""

    def __init__(self, profile_dir, chrome_path="", headless=False):
        self.profile_dir = profile_dir
        self.chrome_path = chrome_path
        self.headless = headless
        self._pw = None
        self._context = None

    def context(self):
        if self._context is not None:
            return self._context
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise AutofillUnavailable("Playwright não instalado. Rode: pip3 install playwright")
        if self._pw is None:
            self._pw = sync_playwright().start()
        os.makedirs(self.profile_dir, exist_ok=True)
        kwargs = {"user_data_dir": self.profile_dir, "headless": self.headless, "no_viewport": True}
        attempts = []
        if self.chrome_path:
            attempts.append({"executable_path": self.chrome_path})
        attempts += [{"channel": "chrome"}, {}]
        last = None
        for extra in attempts:
            try:
                ctx = self._pw.chromium.launch_persistent_context(**kwargs, **extra)
                ctx.on("close", lambda *_: self._forget(ctx))  # voce fechou o Chrome
                self._context = ctx
                return ctx
            except Exception as e:  # canal nao instalado, perfil em uso...
                last = e
        raise AutofillUnavailable(f"não consegui abrir o Chrome: {last}")

    def _forget(self, ctx):
        if self._context is ctx:
            self._context = None

    def close(self):
        try:
            if self._context:
                self._context.close()
        finally:
            self._context = None
            if self._pw:
                self._pw.stop()
                self._pw = None


def fill_page(page, lead_id, url, values, cover_letter_path, answer_fn, timeout_ms=30000):
    """Preenche a pagina ja aberta. `answer_fn(list[str]) -> dict[str, str]`."""
    report = AutofillReport(lead_id=lead_id, url=url, ats=detect_ats(url))
    page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    try:
        page.wait_for_selector("input, textarea", timeout=timeout_ms)
    except Exception:
        report.errors.append("nenhum formulário encontrado na página (pode exigir login ou clique em 'Apply')")
        return report
    fields = [FormField(**f) for f in page.evaluate(SCAN_JS)]
    by_pid = {f.pid: f for f in fields}
    plan = plan_fields(fields, values, cover_letter_path)

    if plan.questions:
        try:
            answers = answer_fn(list(plan.questions.values()))
        except Exception as e:
            answers = {}
            report.errors.append(f"IA não respondeu as perguntas: {e}")
        for pid, label in plan.questions.items():
            if answers.get(label):
                plan.fills[pid] = answers[label]
                report.answered.append(label)
            elif by_pid[pid].required:
                plan.manual.append(by_pid[pid])

    filled_ids = []
    for pid, value in plan.fills.items():
        try:
            page.locator(f'[data-prospector-id="{pid}"]').fill(value, timeout=5000)
            filled_ids.append(pid)
            if by_pid[pid].label not in report.answered:
                report.filled.append(by_pid[pid].label)
        except Exception as e:
            report.errors.append(f"não preenchi '{by_pid[pid].label}': {e.__class__.__name__}")
            plan.manual.append(by_pid[pid])
    for pid, path in plan.files.items():
        try:
            page.locator(f'[data-prospector-id="{pid}"]').set_input_files(path, timeout=10000)
            filled_ids.append(pid)
            report.uploaded.append(f"{by_pid[pid].label or 'arquivo'}: {os.path.basename(path)}")
        except Exception as e:
            report.errors.append(f"não anexei '{os.path.basename(path)}': {e.__class__.__name__}")
            plan.manual.append(by_pid[pid])

    manual_ids = [f.pid for f in plan.manual]
    report.manual = [f.label or f.name for f in plan.manual]
    page.evaluate(MARK_JS, [filled_ids, manual_ids, len(fields)])
    return report


class AutofillWorker:
    """Fila de preenchimentos executada numa thread dedicada ao Playwright."""

    def __init__(self, session):
        self.session = session
        self._jobs = queue.Queue()
        self._thread = None

    def submit(self, lead_id, url, values, cover_letter_path, answer_fn):
        fut = Future()
        self._jobs.put((fut, lead_id, url, values, cover_letter_path, answer_fn))
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._run, name="autofill", daemon=True)
            self._thread.start()
        return fut

    def _run(self):
        while True:
            fut, lead_id, url, values, cl_path, answer_fn = self._jobs.get()
            if fut is None:
                break
            try:
                ctx = self.session.context()
                page = ctx.new_page()
                target = application_url(url)
                page.goto(target, wait_until="domcontentloaded", timeout=45000)
                page.bring_to_front()
                fut.set_result(fill_page(page, lead_id, target, values, cl_path, answer_fn))
            except Exception as e:
                fut.set_exception(e)

    def stop(self):
        self._jobs.put((None,) * 6)
