import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RepositoryDistributionTests(unittest.TestCase):
    def test_github_repository_contract(self):
        required = [
            ".github/workflows/test.yml",
            ".python-version",
            "requirements.txt",
            "pyproject.toml",
            "package.json",
            "package-lock.json",
            "README.md",
            "SKILL.md",
            "LICENSE",
            "agents/openai.yaml",
        ]
        self.assertEqual([], [name for name in required if not (ROOT / name).is_file()])

    def test_dependencies_are_declared(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertIn("openpyxl", requirements)
        self.assertIn("playwright", package.get("dependencies", {}))

    def test_repository_excludes_generated_and_sensitive_artifacts(self):
        forbidden_dirs = {"dist", "outputs", "node_modules", "__pycache__", ".pytest_cache"}
        forbidden_suffixes = {".xlsx", ".jsonl", ".pyc", ".log", ".tmp"}
        bad = []
        for path in ROOT.rglob("*"):
            relative = path.relative_to(ROOT)
            if any(part in forbidden_dirs for part in relative.parts):
                bad.append(str(relative))
            elif path.is_file() and path.suffix.lower() in forbidden_suffixes:
                bad.append(str(relative))
        self.assertEqual([], bad)

    def test_ci_covers_python_node_and_skill_validation(self):
        workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
        self.assertIn("windows-latest", workflow)
        self.assertIn("macos-latest", workflow)
        self.assertIn("ubuntu-latest", workflow)
        self.assertIn("python -m unittest", workflow)
        self.assertIn("npm test", workflow)
        self.assertIn("quick_validate.py", workflow)


if __name__ == "__main__":
    unittest.main()
