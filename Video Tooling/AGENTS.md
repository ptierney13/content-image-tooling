# Riftbound Video Tooling

## Primary Entry Points
- `Image Generation/AGENTS.md`: deck image generation layout, source-of-truth rules, and output organization.
- `Image Generation/Tools/AGENTS.md`: script commands, repeatable regeneration steps, and verification workflow.

## Project Rules
- Keep generated guide images under `Image Generation/output/`.
- Keep shared caches, templates, and reusable reference data under `Image Generation/Data/`.
- Keep scripts, tests, and agent-facing tooling docs under `Image Generation/Tools/`.
- Do not add new workflow-specific folders beside `Data/`, `Tools/`, and `output/` inside `Image Generation/`.

## Agent Workflow
1. Read `Image Generation/AGENTS.md`.
2. Read `Image Generation/Tools/AGENTS.md` before running or changing scripts.
3. Edit deck-specific plans in `Image Generation/output/<Deck Name>/Data/`.
4. Regenerate through the manifest or a specific plan command from `Tools/`.
5. Compare generated images against references before reporting completion.
