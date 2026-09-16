"""Caso de uso: transformar o curriculo original (PDF/DOCX) no CV-mestre estruturado."""
from prospector.adapters.llm_anthropic import text_block
from prospector.adapters.resume_files import content_blocks
from prospector.domain.resume import MasterResume, assign_ids
from prospector.services.prompts import IMPORT_SCHEMA, IMPORT_SYSTEM


class ResumeImportService:
    def __init__(self, llm, store, profile=None):
        self.llm = llm
        self.store = store
        self.profile = profile

    def extract(self, file_path):
        blocks = content_blocks(file_path)
        blocks.append(text_block("Extraia este currículo no formato pedido."))
        data = self.llm.generate_json(IMPORT_SYSTEM, blocks, IMPORT_SCHEMA, "registrar_curriculo",
                                      max_tokens=8000)
        contact = data.setdefault("contact", {})
        if self.profile:  # completa contato com o perfil quando o CV nao traz
            contact.setdefault("name", self.profile.nome)
            if not contact.get("email"):
                contact["email"] = self.profile.email
        return MasterResume.from_dict(assign_ids(data))

    def run(self, file_path):
        resume = self.extract(file_path)
        backup = self.store.save(resume)
        return resume, backup
