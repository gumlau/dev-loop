# shell fixture

This README contains a fenced shell example that puts a `--flag` immediately
after a `VAR=value` env prefix. Bash applies the env prefix to the next
command word, treats `--flag` as the command, and exits 127 with
`command not found`. The lint must catch this class of doc-vs-shell drift
(see LOOP-9).

```
PROJECTS="boardku" --restart  ~/.claude/plugins/data/dev-loop/run-loop.sh
```

The correct forms are:

- `PROJECTS="boardku" RESTART=1 ~/.claude/plugins/data/dev-loop/run-loop.sh` (env var)
- `PROJECTS="boardku" ~/.claude/plugins/data/dev-loop/run-loop.sh --restart` (positional flag, after the script)
