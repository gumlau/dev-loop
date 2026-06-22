# mdlinkfrag fixture

This README links to a real file with a broken fragment:
[broken fragment](other.md#nonexistent-heading) — the file `other.md`
exists, so the existing `md-links` rule passes, but `#nonexistent-heading`
does NOT resolve to any `##`-or-deeper heading in `other.md`, so the new
`md-link-fragments` rule must trip.

As a sanity check, a real fragment alongside it must NOT trip the rule:
[valid](other.md#real-heading).
