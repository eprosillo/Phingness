import json
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "config"
PROFILES_FILE = CONFIG_DIR / "goal_profiles.json"
CURRENT_GOAL_FILE = CONFIG_DIR / "current_goal.json"


def load_profiles() -> dict:
    with open(PROFILES_FILE) as f:
        return json.load(f)


def get_active_goal_name() -> str:
    with open(CURRENT_GOAL_FILE) as f:
        return json.load(f)["active_goal"]


def set_active_goal(name: str):
    profiles = load_profiles()
    if name not in profiles:
        raise ValueError(f"Unknown goal '{name}'. Choose from: {list(profiles)}")
    with open(CURRENT_GOAL_FILE, "w") as f:
        json.dump({"active_goal": name}, f, indent=2)


def get_active_profile() -> tuple[str, dict]:
    name = get_active_goal_name()
    profiles = load_profiles()
    return name, profiles[name]
