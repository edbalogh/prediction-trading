# Update Knowledge Base

You are about to push code to the remote repository. Before doing so, evaluate the current conversation and recent commits for decisions, findings, and patterns worth preserving in the knowledge base.

## What to look for

Review the conversation since the last push (or the full conversation if this is the first push) for:

- **Architecture decisions**: choices about component boundaries, data flow, or structural design
- **Non-obvious API behaviors**: undocumented quirks, edge cases, or gotchas in external APIs
- **Bugs and their fixes**: not the fix itself (that's in the code) but WHY the bug existed and why the fix works
- **Design trade-offs**: things that were consciously chosen over alternatives, with the reasoning
- **Patterns the codebase relies on**: conventions that a reader wouldn't infer from the code alone
- **Things that surprised you**: if something was unexpected, future readers will also be surprised

## What NOT to add

- Code that can be read directly from source files
- Git history (use `git log`)
- Temporary notes or debugging state
- Information already in CLAUDE.md, specs, or plans
- Decisions that are self-evident from the code

## Process

1. Read [knowledge-base/log.md](knowledge-base/log.md) to see what's already recorded (avoid duplicates)
2. Read relevant topic pages if updating an existing topic
3. Identify 0–3 entries worth adding from the current conversation
4. For each entry:
   - Add a brief entry to `knowledge-base/log.md` (date + 1-2 sentence summary)
   - Add or update the appropriate topic page in `knowledge-base/topics/`
   - If the topic doesn't exist, create the file and add it to `knowledge-base/index.md`

## Entry format (topic pages)

```markdown
### [Decision or finding title]

**Date:** YYYY-MM-DD
**Context:** [one sentence: why this came up]

[2-4 sentences on the WHY — not what the code does, but why this approach was chosen or why this behavior exists]
```

## If nothing is worth adding

That's fine. Most pushes won't generate KB entries. Only add an entry if you'd want a new team member (or future you) to know this — not just because something changed.

## After updating

Stage and commit the knowledge-base changes as part of the push:

```bash
git add knowledge-base/
git commit -m "docs: update knowledge base"
```

Then allow the push to proceed.
