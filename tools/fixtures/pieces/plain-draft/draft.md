# Plain Draft *(fixture)*

*Fixture — a composed but unpublished piece. No `public_url`, so the baseline check
must pass over it rather than counting it as out of sync.*

---

## I. One section

A piece that has been composed to a draft post but never published has no public URL.
The sync tools must treat it as not-live,[^1] because a composed draft and a live post
are indistinguishable by `post_url` alone.[^2]

[^1]: The distinction is `public_url` plus presence in the archive.

[^2]: Both carry an editor address; only one is reachable by a reader.
