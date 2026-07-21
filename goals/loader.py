import json
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "config"
PROFILES_FILE = CONFIG_DIR / "goal_profiles.json"
_JSON_FILE = CONFIG_DIR / "current_goal.json"  # used only as fallback default


def load_profiles() -> dict:
    with open(PROFILES_FILE) as f:
        return json.load(f)


def _json_default() -> str:
    try:
        with open(_JSON_FILE) as f:
            return json.load(f)["active_goal"]
    except Exception:
        return next(iter(load_profiles()))


def get_active_goal_name() -> str:
    # Import here to avoid circular imports at module load time
    from training.db import get_setting
    return get_setting("active_goal") or _json_default()


def set_active_goal(name: str):
    profiles = load_profiles()
    if name not in profiles:
        raise ValueError(f"Unknown goal '{name}'. Choose from: {list(profiles)}")
    from training.db import set_setting
    set_setting("active_goal", name)


def get_active_profile() -> tuple[str, dict]:
    name = get_active_goal_name()
    profiles = load_profiles()
    return name, profiles[name]
