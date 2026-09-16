"""Leitura e gravacao do CV-mestre (data/resume.json), com copia da versao anterior."""
import json
import os
import shutil
from datetime import datetime

from prospector.domain.resume import MasterResume, ResumeError, assign_ids


class ResumeStore:
    def __init__(self, path):
        self.path = path

    @property
    def exists(self):
        return os.path.exists(self.path)

    def load(self):
        if not self.exists:
            raise ResumeError(f"CV-mestre não encontrado em {self.path}. Rode "
                              "`python3 prospector.py importar-cv <arquivo.pdf>` primeiro.")
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except ValueError as e:
            raise ResumeError(f"JSON inválido em {self.path}: {e}")
        return MasterResume.from_dict(assign_ids(data))

    def save(self, resume):
        resume.validate()
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        backup = None
        if self.exists:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = f"{os.path.splitext(self.path)[0]}.{stamp}.bak.json"
            shutil.copy2(self.path, backup)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(resume.to_dict(), f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)
        return backup
