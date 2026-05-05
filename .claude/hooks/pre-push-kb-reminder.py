#!/usr/bin/env python3
"""Pre-push hook: reminds to consider updating the knowledge base before pushing."""
import json
import sys

data = json.load(sys.stdin)
command = data.get("tool_input", {}).get("command", "")

if "git push" in command:
    print(json.dumps({
        "permissionDecision": "ask",
        "reason": (
            "Before pushing, consider running /update-knowledge-base to capture any "
            "decisions or findings from this session in the knowledge base."
        ),
    }))
