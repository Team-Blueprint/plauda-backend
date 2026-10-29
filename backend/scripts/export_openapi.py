import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app  # noqa: E402

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "contracts"


def main() -> None:
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    out = CONTRACTS_DIR / "openapi.json"
    out.write_text(json.dumps(app.openapi(), indent=2) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
