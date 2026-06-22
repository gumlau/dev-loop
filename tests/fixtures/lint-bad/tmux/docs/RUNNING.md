# tmux fixture

Fixture for the `tmux-session-name-consistency` lint rule (LOOP-15 →
LOOP-13 AC#4). The launcher (`scripts/run-loop.sh`) only creates
`dev-loop-<project>` sessions; a bare `dev-loop` is stale doc drift.

## Stale form (the rule must trip on this paragraph)

To rejoin a running loop, run:

    tmux attach -t dev-loop

This paragraph deliberately omits every allow-list keyword
(b a r e / d o n ' t / n e v e r / f a i l s / s i l e n t l y /
"no session found" / anti-pattern), so the rule reports it as a finding.

## Correct form (must NOT trip)

The launcher creates `dev-loop-<project>`, so use
`tmux attach -t dev-loop-boardku` (the per-project name).
