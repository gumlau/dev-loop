# extramarketplace fixture

Fixture for the `extramarketplace-source-discriminator` lint rule (LOOP-22 →
LOOP-21). The rule must trip on a fenced JSON snippet that uses a `"source"`
discriminator outside the Claude-Code-accepted set (`directory`/`github`/
`npm`). This is the LOOP-21 pre-fix shape verbatim.

## Bad shape (the rule must trip on this fenced block)

This deliberately omits every allow-list keyword so the rule reports it:

```json
{
  "extraKnownMarketplaces": {
    "dev-loop": { "source": { "source": "local", "path": "/path/to/parent-of-dev-loop" } }
  }
}
```

The block also has no `.claude-plugin/marketplace.json` callout in this
section, so if a future maintainer "fixed" only the discriminator token by
swapping `local` for `directory` the path-correctness sub-check would still
flag it. Both axes LOOP-21 fixed are covered here.
