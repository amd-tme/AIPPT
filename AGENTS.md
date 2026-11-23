# AGENTS.md

Guidance for AI coding assistants working on AIPPT. This is the vendor-neutral
entry point — any agent (Claude Code, Cursor, OpenAI Codex, Aider, Goose,
Gemini CLI, etc.) should read this first.

Read `CONTRIBUTING.md` before making your first change. Apply its workflow in
proportion to the work. The project owner's explicit directions take precedence
over workflow defaults.

## Workflow defaults

Choose the lightest process that makes a change understandable and reviewable.

1. **Planning** — a scoped issue or short plan is sufficient for bounded fixes,
   test repairs, documentation and routine maintenance. Prefer a PRD for new
   features or substantial behavior, architecture or operational changes. Use
   `~/git/swproductmgmt/projects/aippt/PRD-TEMPLATE.md`, fill each section, and
   publish under `projects/aippt/prds/` for review. swproductmgmt's separate
   human-review/merge policy still applies (`/github publish … --no-merge`).
   Review can proceed alongside bounded implementation when the owner agrees.
2. **Branch / worktree** — use a descriptive branch off `main`. An isolated
   worktree is preferred when useful; reusing a suitable clean one is fine.
3. **Verification** — prefer a failing regression test before a behavior fix.
   An existing reproducible failure can provide that baseline. Run checks relevant
   to the change and the fast suite before publishing code when practical.
   Investigate failures and distinguish regressions from existing/environment
   failures; document evidence and limitations rather than hiding them.
4. **Changelog** — record user-visible and material developer-workflow changes
   under `[Unreleased]`. Routine prose edits need no ceremonial entry.
5. **Documentation** — update affected guidance when behavior or setup changes.
   Build Sphinx changes with warnings treated as errors.

Use judgment for routine choices, and explain material deviations in the handoff.
Do not repeatedly ask the owner to approve harmless workflow details. Preserve
separate production, access-control and shared-repository review gates.

## Tool-specific guidance

| Tool                       | File                                            |
| -------------------------- | ----------------------------------------------- |
| Claude Code                | `CLAUDE.md` (project root)                      |
| Cursor                     | `.cursor/rules/` and `.cursor/skills/` symlinks |
| All other agents           | This file + `CONTRIBUTING.md`                   |

Skills (Claude Code / Cursor) live in `skills/` as the source of truth; the
`.claude/skills/` and `.cursor/skills/` directories are symlinks into it.

## Hard nos

These apply to every agent, every time:

- **Never commit to `main` directly.** Always work on a branch.
- **Never commit without an explicit user request.** "Let's implement X"
  is not a commit instruction.
- **Never bypass hooks** (`--no-verify`, `--no-gpg-sign`). If a pre-commit
  hook fails, fix the underlying issue and create a new commit — do not
  `--amend` past a hook failure.
- **Never force-push to `main`.**
- **Never `git add -A` / `git add .`** — stage files by name to avoid
  accidentally committing `.env`, credentials, large binaries, or another
  agent's in-progress work.
- **Never delete unfamiliar files, branches, or worktrees** without
  investigating — they may be another contributor's in-flight work.
- **Never claim a feature works without running it.** Type-check and tests
  verify code correctness, not feature correctness. If you cannot exercise
  the UI or CLI flow yourself, say so explicitly in your handoff.

## Co-author attribution

When you generate meaningful code, add a trailer to the commit message:

```
Co-Authored-By: <Model Name> <noreply@anthropic.com>
```

Use the actual model identifier (`Claude Opus 4.7`, `GPT-5`, etc.) rather
than a generic "AI assistant" label.

## Where to look when stuck

- Process questions → `CONTRIBUTING.md`
- Project conventions, CLI commands, environment setup → `CLAUDE.md`
- Skill catalogue → `SKILLS.md`
- Active PRDs → `~/git/swproductmgmt/projects/aippt/prds/` (shared; branch→PR→reviewed
  and merged by someone else)
- Implemented PRDs (the historical record of how decisions were made) →
  `~/git/swproductmgmt/projects/aippt/prds/implemented/`
- PRD status dashboard → `AIPPT PRD Tracker` note in the Obsidian vault
- Production deployment state → `deploy/slai-app-prod/`
