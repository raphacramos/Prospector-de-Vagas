from prospector.core.config import Color

TEMPLATES = {
    "1": {
        "name": "Modelo 1: Tech Lead / EM (Nacional - Backend & BINGO)",
        "subject": "Aplicação Engenharia Backend - {empresa} - Raphael Ramos",
        "template": (
            "Olá {nome},\n\n"
            "Acompanho a evolução técnica da {empresa} e vi a movimentação no time de engenharia.\n"
            "Sou graduado em Computação pela UFCG, com atuação em pipelines de alta vazão e telemetria em tempo real no radiotelescópio BINGO.\n"
            "Domino Python, PostgreSQL e arquitetura limpa focada em resiliência e concorrência.\n\n"
            "Teria 5 min para um breve alinhamento técnico sobre os desafios atuais do time?\n\n"
            "Abraço,\n"
            "Raphael Ramos\n"
            "linkedin.com/in/raphael-c-1a7430108 • github.com/raphacramos"
        )
    },
    "2": {
        "name": "Modelo 2: CTO / Engineering Lead (Internacional Remoto - English)",
        "subject": "Software Engineer Application - {empresa} - Raphael Ramos",
        "template": (
            "Hi {nome},\n\n"
            "I follow {empresa}'s work and your focus on scaling backend services.\n"
            "Graduating in CS from UFCG, I engineered high-throughput telemetry pipelines with Python, HDF5, and SDR on the BINGO Telescope.\n"
            "My background emphasizes Linux internals, algorithm optimization, and Clean Architecture.\n\n"
            "Open to a brief 5-min chat on how my profile fits your engineering needs?\n\n"
            "Best regards,\n"
            "Raphael Ramos\n"
            "linkedin.com/in/raphael-c-1a7430108 • github.com/raphacramos"
        )
    },
    "3": {
        "name": "Modelo 3: Recrutador Técnico / Talent Acquisition",
        "subject": "Candidatura: {vaga} - {empresa} - Raphael Ramos",
        "template": (
            "Olá {nome},\n\n"
            "Notei a oportunidade de {vaga} na {empresa}.\n"
            "Minha formação na UFCG abrange computação científica, sistemas operacionais e backend com Python, Docker e bancos relacionais.\n"
            "Tenho inglês fluente e experiência como monitor de Algoritmos Avançados (LEDA) e Redes.\n\n"
            "Posso compartilhar meu currículo para avaliação direta junto à liderança técnica?\n\n"
            "Atenciosamente,\n"
            "Raphael Ramos\n"
            "linkedin.com/in/raphael-c-1a7430108 • github.com/raphacramos"
        )
    }
}

def get_message_content(model_key, nome="Hiring Team", empresa="Company", vaga="Software Engineer"):
    config = TEMPLATES.get(str(model_key), TEMPLATES["2"])
    subject = config["subject"].format(nome=nome, empresa=empresa, vaga=vaga)
    body = config["template"].format(nome=nome, empresa=empresa, vaga=vaga)
    return subject, body
