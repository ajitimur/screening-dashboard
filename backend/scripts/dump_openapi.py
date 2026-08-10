"""Write the app's OpenAPI schema to frontend/src/api/openapi.json.

Half of the type-generation loop (spec §7.5): this dumps the schema FastAPI
derives from the Pydantic response models; ``npm run gen:types`` then turns it
into the committed ``schema.d.ts``. Run whenever a response model changes.
"""

import json
import sys
from pathlib import Path

# Make the backend package importable regardless of the working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screener.app import create_app  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "api" / "openapi.json"


def render() -> str:
    """The exact text written to ``openapi.json`` — the single source of truth
    for the serialization, shared with the contract-drift test."""
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render())
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
