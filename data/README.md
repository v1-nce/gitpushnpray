# Competition Data

## `public_set.jsonl`

Contains 200 labeled development sessions: 80 Buying, 80 Browsing, 30 Intent Override, and 10 Boundary sessions.

Each session contains a safe aggregate `user_profile` and public labels for local development. Direct user identifiers, timestamps, free-text reviews, raw purchase history, hidden intent cards, and simulator-policy internals are not shipped in this participant file.

## `catalog.jsonl`

Download `catalog.jsonl.gz` from the GitHub Release and decompress it as `catalog.jsonl` in this directory. Expected row count: 50,000.

Verify the download **before** decompressing. The published `SHA256SUMS` covers the
compressed `catalog.jsonl.gz` only; gzip output is not byte-reproducible across
implementations, so re-compressing `catalog.jsonl` cannot reconstruct that digest.
As a local integrity anchor, the decompressed file used for every result in
`results/` has SHA-256:

```text
b74446b8074ca4f9f83a6041673377ba24af93d853c907bfe92e9a405c40c7b0  catalog.jsonl
```


Never place API keys, private evaluation data, or participant outputs in this directory.
