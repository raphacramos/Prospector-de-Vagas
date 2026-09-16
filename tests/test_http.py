"""Cliente HTTP: fallback para curl so em erro de certificado."""
import ssl
import unittest
import urllib.error
from unittest import mock

from prospector.adapters import http as http_mod


class HttpClientTest(unittest.TestCase):
    def client(self):
        return http_mod.UrllibHttpClient(timeout=1, debug=False)

    def test_timeout_nao_chama_curl(self):
        c = self.client()
        with mock.patch.object(http_mod.urllib.request, "urlopen",
                               side_effect=urllib.error.URLError("timed out")), \
             mock.patch.object(c, "_curl") as curl:
            self.assertIsNone(c.get_text("https://x"))
        curl.assert_not_called()
        self.assertIn("timed out", c.last_error)

    def test_certificado_usa_curl(self):
        c = self.client()
        err = urllib.error.URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED"))
        with mock.patch.object(http_mod.urllib.request, "urlopen", side_effect=err), \
             mock.patch.object(c, "_curl", return_value="ok") as curl:
            self.assertEqual(c.get_text("https://x"), "ok")
        curl.assert_called_once()

    def test_http_404_nao_chama_curl(self):
        c = self.client()
        err = urllib.error.HTTPError("https://x", 404, "nf", {}, None)
        with mock.patch.object(http_mod.urllib.request, "urlopen", side_effect=err), \
             mock.patch.object(c, "_curl") as curl:
            self.assertIsNone(c.get_json("https://x"))
        curl.assert_not_called()
        self.assertEqual(c.last_error, "HTTP 404 em https://x")

    def test_token_github_so_para_api_github(self):
        c = self.client()
        with mock.patch.dict(http_mod.os.environ, {"GITHUB_TOKEN": "t"}):
            self.assertIn("Authorization", c._headers("https://api.github.com/repos/a/b", None))
            self.assertNotIn("Authorization", c._headers("https://evil.example.com/", None))


if __name__ == "__main__":
    unittest.main()
