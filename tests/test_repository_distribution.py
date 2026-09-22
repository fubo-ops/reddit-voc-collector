import json
import subprocess
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
            "scripts/quick_validate.py",
        ]
        self.assertEqual([], [name for name in required if not (ROOT / name).is_file()])

    def test_dependencies_are_declared(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertIn("openpyxl", requirements)
        self.assertIn("playwright", package.get("dependencies", {}))

    def test_git_upload_excludes_generated_and_sensitive_artifacts(self):
        run = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            capture_output=True,
        )
        self.assertEqual(0, run.returncode, run.stderr.decode(errors="replace"))
        names = [name for name in run.stdout.decode().split("\0") if name]
        forbidden_parts = {"dist", "outputs", "node_modules", "__pycache__", ".pytest_cache"}
        forbidden_suffixes = {".xlsx", ".jsonl", ".pyc", ".log", ".tmp", ".har"}
        bad = [
            name for name in names
            if any(part in forbidden_parts for part in Path(name).parts)
            or Path(name).suffix.lower() in forbidden_suffixes
            or Path(name).name in {".env", "SingletonCookie", "SingletonLock", "SingletonSocket"}
        ]
        self.assertEqual([], bad)

    def test_ci_covers_python_node_and_skill_validation(self):
        workflow = (ROOT / ".github/workflows/test.yml").read_text(encoding="utf-8")
        for value in ("windows-latest", "macos-latest", "ubuntu-latest", "python -m unittest", "npm test", "quick_validate.py"):
            self.assertIn(value, workflow)


if __name__ == "__main__":
    unittest.main()
