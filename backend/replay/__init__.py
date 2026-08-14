"""The Qullamaggie trade-record replay study (PRD #114).

A side-car package, sibling to :mod:`screener`, that replays Kullamägi's executed
trades against the app's own funnel, field and rubric. It imports :mod:`screener`
**read-only** and changes nothing in it — no schema migration, no endpoint, no
tab, no constant. Keeping the study in a separate package is the guard against
study constants drifting into the app's constants (PRD user story 29).

Ticket #115 lays the substrate every later ticket (A1/A2/A3) stands on: a
purpose-built replay store holding only US bars over the window, and the parsed,
classified reference set with a count report. Nothing here ever writes to the
live store — the replay store is a fresh file, and the live store is opened
read-only, so the study is structurally incapable of corrupting live history
(PRD user story 28).
"""
