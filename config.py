import os


def _load_env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        print(f"{path} file not found. Shutting down.")
        exit(1)

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)

_load_env_file()

TOKEN = os.getenv("TOKEN")
URL = os.getenv("URL")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
