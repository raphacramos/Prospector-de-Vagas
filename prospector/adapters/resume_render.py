"""Renderiza o CV adaptado em HTML (A4, uma pagina) para virar PDF no Chrome."""
from html import escape

LABELS = {
    "pt": {"summary": "Resumo", "experience": "Experiência", "projects": "Projetos",
           "education": "Formação", "skills": "Competências", "languages": "Idiomas",
           "certifications": "Certificações"},
    "en": {"summary": "Summary", "experience": "Experience", "projects": "Projects",
           "education": "Education", "skills": "Skills", "languages": "Languages",
           "certifications": "Certifications"},
}

CSS = """
@page { size: A4; margin: 13mm 14mm; }
* { box-sizing: border-box; }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: #1b1f23; font-size: 9.6pt;
       line-height: 1.38; margin: 0; }
header { border-bottom: 1.2pt solid #1b1f23; padding-bottom: 6pt; margin-bottom: 8pt; }
h1 { font-size: 19pt; margin: 0; letter-spacing: -0.2pt; }
.subtitle { font-size: 10.5pt; margin-top: 2pt; color: #33404d; }
.contact { font-size: 8.8pt; color: #4a5561; margin-top: 3pt; }
.contact span + span::before { content: "  ·  "; }
h2 { font-size: 9pt; text-transform: uppercase; letter-spacing: 1.1pt; margin: 10pt 0 4pt;
     color: #0d5c4a; }
.item { margin-bottom: 6pt; page-break-inside: avoid; }
.row { display: flex; justify-content: space-between; gap: 8pt; }
.role { font-weight: 700; }
.org { color: #33404d; }
.when { color: #5b6670; white-space: nowrap; font-size: 8.8pt; }
ul { margin: 2pt 0 0; padding-left: 12pt; }
li { margin: 1pt 0; }
p { margin: 0; }
.skills { font-size: 9.2pt; }
@media screen { body { max-width: 190mm; margin: 0 auto; padding: 14mm 12mm; } }
"""


def _e(s):
    return escape(s or "")


LETTER_CSS = """
@page { size: A4; margin: 20mm 22mm; }
body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; color: #1b1f23;
       font-size: 11pt; line-height: 1.5; margin: 0; }
header { margin-bottom: 14pt; }
h1 { font-size: 14pt; margin: 0 0 3pt; }
.heading { font-size: 10pt; color: #5b6670; }
p { margin: 0 0 10pt; }
@media screen { body { max-width: 170mm; margin: 0 auto; padding: 20mm; } }
"""


def render_cover_letter_html(text, name="", heading=""):
    """Carta de apresentacao em HTML simples (A4, uma pagina) para virar PDF."""
    body = (text or "").strip()
    # A IA costuma separar paragrafos com linha em branco; se nao tiver, cada quebra de
    # linha simples ja e um paragrafo (carta corrida sem \n\n nao vira um bloco so).
    sep = "\n\n" if "\n\n" in body else "\n"
    paragraphs = "".join(f"<p>{_e(p)}</p>" for p in body.split(sep) if p.strip())
    out = ["<!doctype html><html lang=\"pt\"><head><meta charset=\"utf-8\">",
           f"<title>{_e(name)}</title><style>{LETTER_CSS}</style></head><body>"]
    if name or heading:
        out.append("<header>")
        if name:
            out.append(f"<h1>{_e(name)}</h1>")
        if heading:
            out.append(f'<div class="heading">{_e(heading)}</div>')
        out.append("</header>")
    out.append(paragraphs or f"<p>{_e(body)}</p>")
    out.append("</body></html>")
    return "".join(out)


def _dates(start, end):
    return " – ".join(x for x in (start, end) if x)


def render_html(data):
    """`data` vem de domain.resume.resolve()."""
    lang = data["language"] if data["language"] in LABELS else "en"
    L = LABELS[lang]
    c = data["contact"]
    contact_bits = [c.email, c.phone, c.location] + list(c.links)
    out = [f"<!doctype html><html lang=\"{lang}\"><head><meta charset=\"utf-8\">",
           f"<title>{_e(c.name)}</title><style>{CSS}</style></head><body>",
           "<header>", f"<h1>{_e(c.name)}</h1>"]
    if data["headline"]:
        out.append(f'<div class="subtitle">{_e(data["headline"])}</div>')
    out.append('<div class="contact">' + "".join(f"<span>{_e(b)}</span>" for b in contact_bits if b) + "</div>")
    out.append("</header>")

    if data["summary"]:
        out += [f"<h2>{L['summary']}</h2>", f"<p>{_e(data['summary'])}</p>"]

    if data["experiences"]:
        out.append(f"<h2>{L['experience']}</h2>")
        for exp, bullets in data["experiences"]:
            org = " · ".join(x for x in (exp.company, exp.location) if x)
            out.append('<div class="item"><div class="row">'
                       f'<div><span class="role">{_e(exp.role)}</span> — <span class="org">{_e(org)}</span></div>'
                       f'<div class="when">{_e(_dates(exp.start, exp.end))}</div></div>')
            if bullets:
                out.append("<ul>" + "".join(f"<li>{_e(b.text)}</li>" for b in bullets) + "</ul>")
            out.append("</div>")

    if data["projects"]:
        out.append(f"<h2>{L['projects']}</h2>")
        for proj, bullets in data["projects"]:
            title = _e(proj.name) + (f' <span class="org">· {_e(proj.link)}</span>' if proj.link else "")
            out.append(f'<div class="item"><div class="role">{title}</div>')
            if proj.description and not bullets:
                out.append(f"<p>{_e(proj.description)}</p>")
            if bullets:
                out.append("<ul>" + "".join(f"<li>{_e(b.text)}</li>" for b in bullets) + "</ul>")
            out.append("</div>")

    if data["education"]:
        out.append(f"<h2>{L['education']}</h2>")
        for ed in data["education"]:
            out.append('<div class="item"><div class="row">'
                       f'<div><span class="role">{_e(ed.degree)}</span> — <span class="org">{_e(ed.institution)}</span></div>'
                       f'<div class="when">{_e(_dates(ed.start, ed.end))}</div></div>')
            if ed.details:
                out.append(f"<p>{_e(ed.details)}</p>")
            out.append("</div>")

    if data["skills"]:
        out += [f"<h2>{L['skills']}</h2>", f'<p class="skills">{_e(", ".join(data["skills"]))}</p>']
    extras = [(L["languages"], data["languages"]), (L["certifications"], data["certifications"])]
    for label, values in extras:
        if values:
            out += [f"<h2>{label}</h2>", f"<p>{_e(', '.join(values))}</p>"]
    out.append("</body></html>")
    return "".join(out)
