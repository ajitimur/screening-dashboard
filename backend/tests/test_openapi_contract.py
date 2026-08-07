"""The backend half of the contract-drift check (spec §4.9, issue #74).

``dump_openapi.py`` derives ``frontend/src/api/openapi.json`` from the Pydantic
response models; ``npm run gen:types`` turns that into the committed
``schema.d.ts``. The whole chain is manual, so an edit to a response model that
is never regenerated silently drifts the frontend contract out of date.

The shell command ``scripts/check-types.sh`` guards the *whole* chain (it
regenerates both artefacts and fails if the working tree moved). This test
guards the source-of-truth half inside the ordinary ``npm run test`` suite: the
committed ``openapi.json`` must be byte-for-byte what ``dump_openapi.py`` writes
today. It is the fast feedback that catches a stale schema at model-edit time
rather than later, at a frontend type error.
"""

from scripts.dump_openapi import OUT as OPENAPI_PATH
from scripts.dump_openapi import render


def test_committed_openapi_matches_response_models() -> None:
    committed = OPENAPI_PATH.read_text()
    assert committed == render(), (
        "frontend/src/api/openapi.json is stale relative to the response models. "
        "Run 'npm run gen:types' and commit the regenerated openapi.json and "
        "schema.d.ts."
    )
