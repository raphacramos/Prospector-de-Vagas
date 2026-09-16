"""Dublês compartilhados pelos testes."""
import json
import os

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture_text(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


class FakeHttp:
    """Mapeia trecho de URL -> nome do fixture (ou None para simular falha)."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.last_error = None

    def _find(self, url):
        self.calls.append(url)
        for fragment, name in self.routes.items():
            if fragment in url:
                if name is None:
                    self.last_error = "HTTP 404"
                    return None
                return fixture_text(name)
        self.last_error = "rota não mapeada"
        return None

    def get_text(self, url, headers=None):
        return self._find(url)

    def get_json(self, url, headers=None):
        text = self._find(url)
        return json.loads(text) if text is not None else None
