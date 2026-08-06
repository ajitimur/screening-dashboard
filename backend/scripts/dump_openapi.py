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


def main() -> None:
    schema = create_app().openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
