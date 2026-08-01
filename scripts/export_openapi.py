"""Export the FastAPI OpenAPI schema to frontend/openapi.json."""

import json
from pathlib import Path

from pelican_town_specials.api.app import create_app


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    frontend_dir = repo_root / "frontend"
    frontend_dir.mkdir(parents=True, exist_ok=True)
    output_path = frontend_dir / "openapi.json"
    schema = create_app().openapi()
    output_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
