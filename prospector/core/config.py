import os

# Raiz do projeto (diretório acima de prospector/)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Arquivos pessoais e gerados ficam em data/ (ignorado pelo git)
DATA_DIR = os.path.join(ROOT_DIR, "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "out")


def resolve_asset(filename):
    """Procura o arquivo em data/ e depois na raiz (local antigo). Se nao existir, aponta para data/."""
    for folder in (DATA_DIR, ROOT_DIR):
        candidate = os.path.join(folder, filename)
        if os.path.exists(candidate):
            return candidate
    return os.path.join(DATA_DIR, filename)


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    return OUTPUT_DIR


DB_PATH = os.path.join(ROOT_DIR, "prospector.db")
PDF_EN = resolve_asset("Curriculo_Raphael_Ramos_EN.pdf")
PDF_PT = resolve_asset("Curriculo_Raphael_Ramos_PT_Destaque.pdf")
HTML_EN = resolve_asset("curriculo_en.html")
HTML_PT = resolve_asset("curriculo_pt_destaque.html")
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
