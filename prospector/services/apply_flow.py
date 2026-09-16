"""Caso de uso: abrir o formulario da vaga ja preenchido com o pacote preparado."""
import os
import webbrowser

from prospector.adapters.autofill.fields import application_url, profile_values
from prospector.services.application import ApplicationError


class ApplyFlow:
    def __init__(self, app_service, profile, resume_store, worker=None, opener=webbrowser.open):
        self.app = app_service
        self.profile = profile
        self.resume_store = resume_store
        self.worker = worker
        self._open = opener

    def values(self, lead_id):
        pkg = self.app.load(lead_id)
        if not pkg:
            raise ApplicationError(f"prepare a candidatura do lead #{lead_id} antes de aplicar")
        master = self.resume_store.load() if self.resume_store.exists else None
        return pkg, profile_values(self.profile, master, pkg)

    def start(self, lead_id):
        """Retorna ('autofill', Future) ou ('manual', dict com os valores para copiar)."""
        pkg, values = self.values(lead_id)
        if not pkg.apply_url:
            raise ApplicationError("a vaga não tem link de candidatura")
        cover_path = pkg.cover_letter_pdf or os.path.join(pkg.folder, "carta.txt")
        if self.worker is not None:
            fut = self.worker.submit(lead_id, pkg.apply_url, values, cover_path,
                                     lambda qs: self.app.answer_questions(lead_id, qs),
                                     answers=self.profile.standard_answers)
            return "autofill", fut
        self._open(application_url(pkg.apply_url))
        return "manual", {"url": application_url(pkg.apply_url), "values": values}
