# Sharing debug logs with the agent

Debug logs are ignored globally (see the root `.gitignore`) to avoid accidentally committing large or sensitive runtime output. If you need the agent to review a specific log, you can check it into the repository under this folder.

## How to provide logs
- Place sanitized copies of your debug logs in this directory. You can use `.log`, `.txt`, `.md`, or `.json` extensions; `.log` files inside this folder are explicitly whitelisted despite the global ignore rule.
- Include enough context in the filename to identify the scenario (e.g., `naive_agent_showcase_round1.log`).
- Avoid including secrets or PII; redact as needed before committing.

## Why this folder exists
Negation rules in `.gitignore` allow committed logs **only** from `docs/debug_logs/`. This keeps transient runtime logs out of version control while giving you a dedicated place to store representative traces for debugging and review.
