"""Taxonomia de skills e calibracao do curriculo."""
import unittest

from prospector.engine.tailor import extract_canonical_skills


class SkillsRegexTest(unittest.TestCase):
    def test_cpp(self):
        self.assertIn("C/C++", extract_canonical_skills("Strong C++ skills."))
        self.assertIn("C/C++", extract_canonical_skills("Experience in C/C++ required"))

    def test_go_nao_confunde_com_verbo(self):
        self.assertNotIn("Go", extract_canonical_skills("You will go above and beyond."))
        self.assertNotIn("Go", extract_canonical_skills("Go beyond the basics."))

    def test_go_linguagem(self):
        self.assertIn("Go", extract_canonical_skills("Backend in Go and Rust"))
        self.assertIn("Go", extract_canonical_skills("experience with golang"))

    def test_big_o(self):
        self.assertIn("Algorithms & Data Structures", extract_canonical_skills("reason about O(n) costs"))


if __name__ == "__main__":
    unittest.main()
