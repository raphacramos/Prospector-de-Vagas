"""Cliente da API da Anthropic (Messages API) so com a biblioteca padrao.

Usa tool use com `tool_choice` forcado para receber JSON estruturado. A chave vem de
ANTHROPIC_API_KEY (no .env ou no ambiente) e nunca e gravada em arquivo pelo Prospector.
"""
import json
import os
import time
import urllib.error
import urllib.request

from prospector.ports import LlmError

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5"
RETRY_STATUS = {429, 500, 502, 503, 529}


def validate_schema(value, schema, path="$"):
    """Validacao minima de JSON Schema (type, required, properties, items, enum)."""
    types = {"object": dict, "array": list, "string": str, "boolean": bool,
             "integer": int, "number": (int, float)}
    expected = schema.get("type")
    if expected:
        wrong_type = not isinstance(value, types[expected])
        if expected in ("integer", "number") and isinstance(value, bool):
            wrong_type = True
        if wrong_type:
            raise LlmError(f"resposta da IA inválida em {path}: esperado {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise LlmError(f"resposta da IA inválida em {path}: valor fora de {schema['enum']}")
    if expected == "object":
        for key in schema.get("required", []):
            if key not in value:
                raise LlmError(f"resposta da IA inválida: falta '{key}' em {path}")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                validate_schema(value[key], sub, f"{path}.{key}")
    if expected == "array" and "items" in schema:
        for i, item in enumerate(value):
            validate_schema(item, schema["items"], f"{path}[{i}]")
    return value


def text_block(text):
    return {"type": "text", "text": text}


def pdf_block(b64_data):
    return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64_data}}


class AnthropicClient:
    def __init__(self, api_key=None, model=None, timeout=120, max_retries=3, opener=None, sleep=time.sleep):
        self.api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or os.environ.get("PROSPECTOR_MODEL") or DEFAULT_MODEL
        self.timeout = timeout
        self.max_retries = max_retries
        self._open = opener or urllib.request.urlopen
        self._sleep = sleep
        self.usage = {"input_tokens": 0, "output_tokens": 0}

    @property
    def configured(self):
        return bool(self.api_key)

    def generate_json(self, system, content, schema, tool_name, max_tokens=4096):
        if not self.api_key:
            raise LlmError("ANTHROPIC_API_KEY não definida. Crie uma chave em console.anthropic.com "
                           "e coloque ANTHROPIC_API_KEY=... no arquivo .env do projeto.")
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": content}],
            "tools": [{"name": tool_name, "description": "Registra o resultado estruturado.",
                       "input_schema": schema}],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        data = self._post(body)
        self.usage["input_tokens"] += data.get("usage", {}).get("input_tokens", 0)
        self.usage["output_tokens"] += data.get("usage", {}).get("output_tokens", 0)
        if data.get("stop_reason") == "max_tokens":
            raise LlmError("a resposta da IA foi cortada (max_tokens); tente de novo com um CV menor")
        for block in data.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == tool_name:
                return validate_schema(block.get("input") or {}, schema)
        raise LlmError("a IA não devolveu o resultado estruturado")

    def _post(self, body):
        payload = json.dumps(body).encode("utf-8")
        last = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(API_URL, data=payload, method="POST", headers={
                "x-api-key": self.api_key, "anthropic-version": API_VERSION,
                "content-type": "application/json",
            })
            try:
                with self._open(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                detail = _error_message(e)
                if e.code == 401:
                    raise LlmError("chave da API recusada (401). Confira ANTHROPIC_API_KEY no .env")
                if e.code not in RETRY_STATUS or attempt == self.max_retries:
                    raise LlmError(f"erro da API ({e.code}): {detail}")
                last = f"{e.code}: {detail}"
                wait = _retry_after(e) or 2 ** attempt * 2
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt == self.max_retries:
                    raise LlmError(f"sem conexão com a API da Anthropic: {e}")
                last = str(e)
                wait = 2 ** attempt * 2
            self._sleep(wait)
        raise LlmError(f"falha ao chamar a IA: {last}")


def _error_message(err):
    try:
        data = json.loads(err.read().decode("utf-8"))
        return data.get("error", {}).get("message") or str(data)[:200]
    except Exception:
        return str(err)


def _retry_after(err):
    try:
        return min(float(err.headers.get("retry-after", "")), 60)
    except (TypeError, ValueError, AttributeError):
        return None
