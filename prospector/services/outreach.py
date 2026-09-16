"""Caso de uso: montar a mensagem certa para o lead e registrar o resultado no funil."""
import os

from prospector.adapters.senders import OutreachMessage, SendResult
from prospector.domain.lead import LeadStatus

UNKNOWN_COMPANY_LABEL = "empresa-nao-identificada"


class OutreachError(Exception):
    pass


def render_template(profile, key, empresa, vaga, nome=None):
    t = profile.template(key)
    values = {"empresa": empresa, "vaga": vaga, "nome": nome or t.saudacao_padrao,
              "meu_nome": profile.nome, "assinatura": profile.assinatura}
    try:
        return t.assunto.format(**values), t.corpo.format(**values)
    except (KeyError, IndexError) as e:
        raise OutreachError(f"template '{key}' usa um campo desconhecido: {e}. "
                            f"Disponíveis: {', '.join('{' + k + '}' for k in values)}")


class OutreachService:
    def __init__(self, repo, profile):
        self.repo = repo
        self.profile = profile

    def default_template_key(self, lead):
        return "intl" if lead.is_international else "br"

    def build_message(self, lead, template_key=None, nome=None):
        key = template_key or self.default_template_key(lead)
        subject, body = render_template(self.profile, key, lead.company, lead.title, nome)
        language = self.profile.template(key).idioma
        return OutreachMessage(
            lead_id=lead.id, to=lead.primary_email, subject=subject, body=body,
            attachment=self.profile.cv_path(f"pdf_{language}"), language=language, template_key=key,
            from_name=self.profile.nome, from_addr=self.profile.email,
        )

    def warnings(self, lead, msg):
        out = []
        if len(msg.body) > self.profile.max_caracteres_mensagem:
            out.append(f"mensagem com {len(msg.body)} caracteres (limite do perfil: "
                       f"{self.profile.max_caracteres_mensagem})")
        if UNKNOWN_COMPANY_LABEL in lead.labels:
            out.append("empresa não identificada no anúncio; revise o texto antes de enviar")
        if msg.attachment and not os.path.exists(msg.attachment):
            out.append(f"currículo não encontrado: {msg.attachment}")
        return out

    def send(self, lead, sender, template_key=None, nome=None, allow_no_attachment=False, dry_run=False):
        msg = self.build_message(lead, template_key, nome)
        if sender.requires_email and not msg.to:
            raise OutreachError(f"lead #{lead.id} não tem e-mail direto cadastrado")
        if dry_run:  # mostra a mensagem como ficaria; problemas aparecem em warnings()
            return msg, SendResult(False, "dry-run (nada enviado, funil inalterado)")
        if msg.attachment and not os.path.exists(msg.attachment):
            if sender.delivers and not allow_no_attachment:
                raise OutreachError(f"currículo não encontrado: {msg.attachment}. Coloque o PDF em data/ "
                                    "(ou na raiz) ou use --sem-anexo. Nada foi enviado.")
            msg.attachment = None

        result = sender.send(msg)
        status = LeadStatus.MENSAGEM_ENVIADA if result.delivered else LeadStatus.RASCUNHO_ABERTO
        self.repo.set_status(lead.id, status, note=f"{result.detail} [{msg.template_key}]")
        return msg, result

    def followup_text(self, lead):
        lang = "en" if lead.is_international else "pt"
        text = self.profile.followups.get(lang, "")
        return text.format(empresa=lead.company, vaga=lead.title)
