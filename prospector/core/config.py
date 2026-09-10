import os

# Raiz do projeto (diretório acima de prospector/)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB_PATH = os.path.join(ROOT_DIR, "prospector.db")
PDF_EN = os.path.join(ROOT_DIR, "Curriculo_Raphael_Ramos_EN.pdf")
PDF_PT = os.path.join(ROOT_DIR, "Curriculo_Raphael_Ramos_PT_Destaque.pdf")
HTML_EN = os.path.join(ROOT_DIR, "curriculo_en.html")
HTML_PT = os.path.join(ROOT_DIR, "curriculo_pt_destaque.html")
ENV_PATH = os.path.join(ROOT_DIR, ".env")

class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    DIM = "\033[2m"

def load_env():
    """Carrega variáveis do arquivo .env se existir."""
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().replace('"', '').replace("'", ''))

# Alias para compatibilidade
BASE_DIR = ROOT_DIR
