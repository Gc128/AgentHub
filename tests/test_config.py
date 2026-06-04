from pathlib import Path

from agenthub.config import ENV_FILE, PROJECT_ROOT, Settings


def test_settings_env_file_uses_project_root() -> None:
    env_file = Settings.model_config["env_file"]

    assert Path(env_file).is_absolute()
    assert Path(env_file) == ENV_FILE
    assert ENV_FILE == PROJECT_ROOT / ".env"
