from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import translate
from translate import Translator, default_translation, save_template

ROOT = Path(__file__).resolve().parent.parent


def test_importing_translate_writes_no_file(tmp_path):
    # constants.py puts the lang folder in the folder of sys.argv[0], which is the script here
    (tmp_path / "lang").mkdir()
    script = tmp_path / "start.py"
    script.write_text("import translate\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(ROOT)},
    )

    assert result.returncode == 0, result.stderr
    assert sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")) == ["lang", "start.py"]


def test_save_template_writes_the_english_strings(tmp_path):
    save_template(tmp_path)

    assert [path.name for path in tmp_path.iterdir()] == ["English.json"]
    assert json.loads((tmp_path / "English.json").read_text(encoding="utf-8")) == default_translation


def test_a_language_file_cannot_rename_its_language(monkeypatch, tmp_path):
    (tmp_path / "Polski.json").write_text(json.dumps({"language_name": "Hacked"}), encoding="utf-8")
    monkeypatch.setattr(translate, "LANG_PATH", tmp_path)
    translator = Translator()

    translator.set_language("Polski")

    assert translator.current == "Polski"
