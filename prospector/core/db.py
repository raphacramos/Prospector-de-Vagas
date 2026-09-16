"""Fabrica do repositorio de leads (ponto unico para o caminho do banco)."""
import os

from prospector.adapters.storage import SqliteLeadRepository
from prospector.core import config


def get_repository(db_path=None):
    db_path = db_path or config.DB_PATH
    if os.path.dirname(os.path.abspath(db_path)) == os.path.abspath(config.ROOT_DIR):
        backup_dir = os.path.join(config.DATA_DIR, "backups")  # banco antigo na raiz
    else:
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "backups")
    return SqliteLeadRepository(db_path, backup_dir=backup_dir)
