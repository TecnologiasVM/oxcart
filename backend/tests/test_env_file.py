"""The repository's environment file is read before any setting, for the backend and the eval alike.

Each case runs in a fresh Python process (a setting is read once, when its module is first imported), with a
made-up environment file named by OXCART_ENV_FILE. Before the fix, ``app.main`` imported ``app.settings``
before ``oxcart.config`` loaded the file, so a value written only in the file never reached the settings.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
MADE_UP = {"ASK_PASSAGES": "7", "OXCART_API": "http://made-up.invalid:9"}


def run(code: str, env_file: Path, **real: str) -> str:
    env = {k: v for k, v in os.environ.items() if k not in MADE_UP and k != "OXCART_ENV_FILE"}
    env.update(real, OXCART_ENV_FILE=str(env_file), PYTHONPATH=os.pathsep.join([str(BACKEND), str(REPO)]))
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    return done.stdout.strip().splitlines()[-1]


def made_up_file(tmp_path: Path) -> Path:
    path = tmp_path / "made-up-env"
    path.write_text("".join(f"{k}={v}\n" for k, v in MADE_UP.items()), encoding="utf-8")
    return path


def test_a_value_only_in_the_file_reaches_the_settings_whatever_is_imported_first(tmp_path):
    path = made_up_file(tmp_path)
    # the order main.py imports in: the answer model (and with it the settings) before oxcart.config
    assert run("import app.main; from app import settings; print(settings.ASK_PASSAGES)", path) == "7"
    assert run("from app import settings; print(settings.ASK_PASSAGES)", path) == "7"


def test_a_real_environment_variable_wins_over_the_file(tmp_path):
    path = made_up_file(tmp_path)
    assert run("import app.main; from app import settings; print(settings.ASK_PASSAGES)", path, ASK_PASSAGES="4") == "4"


def test_the_eval_reads_the_file_too(tmp_path):
    path = made_up_file(tmp_path)
    assert run("from eval import chat_arm; print(chat_arm.API)", path) == MADE_UP["OXCART_API"]


TEMPLATE = REPO / ".env.example"


def test_the_template_as_copied_leaves_the_backend_and_the_eval_on_the_local_weaviate():
    # "cp .env.example .env" (README, Run it locally) must not name a Weaviate Cloud cluster: a non-empty
    # WEAVIATE_URL sends the backend (ask_service) and the eval (eval/stores.py) to connect_to_weaviate_cloud
    code ="import os, app.main; from app import settings; import eval.stores; print(repr((settings.WEAVIATE_URL, os.environ.get('WEAVIATE_URL', ''))))"
    env = {k: v for k, v in os.environ.items() if k != "WEAVIATE_URL"}
    env.update(OXCART_ENV_FILE=str(TEMPLATE), PYTHONPATH=os.pathsep.join([str(BACKEND), str(REPO)]))
    done = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.strip().splitlines()[-1] == "('', '')"


def test_the_template_names_the_model_key():
    names = [line.split("=", 1)[0].lstrip("# ").strip() for line in TEMPLATE.read_text(encoding="utf-8").splitlines() if "=" in line]
    assert "ANTHROPIC_API_KEY" in names


def test_with_no_file_the_defaults_stand(tmp_path):
    assert run("from app import settings; print(settings.ASK_PASSAGES)", tmp_path / "no-such-file") == "5"
