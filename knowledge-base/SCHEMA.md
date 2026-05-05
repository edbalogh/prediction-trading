# Knowledge Base Schema

This is an AI-maintained knowledge base for the prediction-trading project.
It captures architecture decisions, design rationale, API quirks, and non-obvious patterns
that are not obvious from reading the code or git history.

## Structure

```
knowledge-base/
├── SCHEMA.md          # This file — schema and update instructions
├── index.md           # Topic index
├── log.md             # Chronological log of significant decisions
└── topics/
    ├── architecture.md
    ├── decisions.md
    ├── kalshi-api.md
    └── nautilus-integration.md
```

## What belongs here

- Architecture decisions and the reasoning behind them
- Non-obvious API behaviors (edge cases, undocumented quirks)
- Design trade-offs that were consciously made
- Patterns and conventions that the codebase relies on
- Bugs that were fixed and why the fix works
- Things that surprised the team or would surprise a new reader

## What does NOT belong here

- Code snippets that can be read directly from the source
- Git history (use `git log` / `git blame`)
- Debugging notes or temporary state
- Anything already in CLAUDE.md, specs, or plans

## Update Instructions (for AI agents)

When updating this knowledge base:

1. **Add to `log.md`**: A brief entry with date, what changed, and why it matters.
2. **Update or create a topic page**: If the decision/finding fits an existing topic, update it. Otherwise create a new file in `topics/` and add it to `index.md`.
3. **Be concise**: Each entry should be 2-5 sentences. Explain the WHY, not the WHAT.
4. **One entry per distinct decision/finding**: Don't batch unrelated changes into a single entry.
5. **Never delete history from `log.md`**: Append only.

## Entry Format (topic pages)

```markdown
### [Topic title]

**Date:** YYYY-MM-DD
**Context:** [one sentence on why this came up]

[2-4 sentences on the decision or finding, focused on WHY]
```
