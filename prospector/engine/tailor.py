import os
import re
from prospector.core.config import Color, HTML_EN, HTML_PT, BASE_DIR
from prospector.core.utils import compile_html_to_pdf
from prospector.engine.copywriter import get_message_content

def tailor_cv(empresa, vaga="Software Engineer", skills=None, jd_text="", lang="en"):
    """Gera versão sob medida do currículo alinhada com as palavras-chave da vaga."""
    print(f"\n{Color.CYAN}🎯 Iniciando CV Tailoring Engine para: {Color.BOLD}{empresa}{Color.RESET}")
    clean_empresa = re.sub(r"[^a-zA-Z0-9]", "_", empresa)

    target_skills = []
    if skills:
        target_skills = [s.strip() for s in skills.split(",") if s.strip()]
    if jd_text:
        potential_kw = [
            "FastAPI", "Django", "Flask", "PostgreSQL", "Redis", "Docker", "Kubernetes",
            "Distributed Systems", "Concurrency", "High Throughput", "Telemetry",
            "Machine Learning", "Data Pipelines", "HDF5", "Kafka", "RabbitMQ", "Microservices",
            "Clean Architecture", "Linux", "AsyncIO", "REST APIs", "C++", "Go"
        ]
        for kw in potential_kw:
            if re.search(r"\b" + re.escape(kw) + r"\b", jd_text, re.IGNORECASE):
                if kw not in target_skills:
                    target_skills.append(kw)

    print(f"Palavras-chave destacadas para alinhamento: {Color.GREEN}{', '.join(target_skills) if target_skills else 'Python, Backend, Distributed Systems'}{Color.RESET}")

    base_html_path = HTML_EN if lang == "en" else HTML_PT
    with open(base_html_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    highlight_tag = target_skills[0] if target_skills else "Distributed Telemetry"
    new_headline = f"Software Engineer | Backend & Data Systems | Python, Linux, {highlight_tag}"
    html_content = re.sub(
        r'<div class="subtitle">.*?</div>',
        f'<div class="subtitle">{new_headline}</div>',
        html_content
    )

    output_html_name = f"curriculo_tailored_{clean_empresa}.html"
    output_html_path = os.path.join(BASE_DIR, output_html_name)
    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"📄 Arquivo HTML customizado gerado: {Color.BOLD}{output_html_name}{Color.RESET}")

    output_pdf_name = f"Curriculo_Raphael_Ramos_{clean_empresa}.pdf"
    output_pdf_path = os.path.join(BASE_DIR, output_pdf_name)

    print(f"⚙️ Compilando PDF sob medida via Chrome headless...")
    success = compile_html_to_pdf(output_html_path, output_pdf_path, timeout=30)
    if success:
        print(f"{Color.GREEN}{Color.BOLD}✅ PDF sob medida gerado com sucesso: {output_pdf_name}!{Color.RESET}")
    else:
        print(f"{Color.YELLOW}⚠️ HTML pronto. Para gerar o PDF, abra {output_html_name} e imprima como PDF.{Color.RESET}")

    model = "2" if lang == "en" else "1"
    subj, msg = get_message_content(model, nome="Team", empresa=empresa, vaga=vaga)
    print(f"\n{Color.BOLD}--- Mensagem de Abordagem Sob Medida para {empresa} ---{Color.RESET}")
    print(f"Assunto: {subj}\n")
    print(msg)
    print("-" * 65 + "\n")
