# Authoring guidance

## Architecture

Use groups for trust zones, tiers, regions, or bounded contexts. Label edges with protocols or events only when that information changes the reader's understanding. Make external systems visually distinct.

## Flowchart

Use `process` for actions, `decision` for questions, `document` for generated artifacts, and short verb phrases for labels. Use `TB` unless a horizontal process is materially easier to scan.

## Data flow

Use `data` edges and name the payload rather than the transport when the payload matters more. Use `database` for durable storage and `queue` for asynchronous boundaries.

## UML-style component view

Represent deployable or independently owned components as nodes. Use `dependency` edges for compile/runtime dependencies and `association` only for neutral relations. Do not imply strict UML semantics unless the source supports them.

## ERD

For the first release, model each table as a `database` node and put key fields in `description`. Use edge labels for cardinality and foreign-key names. Prefer a dedicated ERD importer when column-level compartments become necessary.

## Scope control

Aim for 5–15 nodes per page. Above 20 nodes, create a context view plus a detailed view. Preserve one primary reading path and move operational trivia to notes or documentation.
