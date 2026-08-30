# Participant Release Checklist

## Code and reproducibility

- [x] `starter.agent.Agent` implements the required interface.
- [x] The agent runs without network access, credentials, or third-party packages.
- [x] Unit tests pass from a clean checkout with the documented command.
- [x] The official public evaluator result is reproducible.
- [x] The catalog-disjoint shadow benchmark uses a fixed seed and emits no target IDs.
- [ ] Verify the catalog checksum on the final submission machine.
- [ ] Measure cold-start peak memory and per-response p50/p95 latency.
- [ ] Test the exact archive or repository commit submitted to Devpost.

## Documentation and disclosure

- [x] README includes setup, evaluation, shadow benchmark, cost, and limitations.
- [x] Model/API choice and zero-token usage are disclosed.
- [x] Public-development and synthetic-shadow results are clearly separated.
- [ ] Add every team member's name and concrete contribution to the submission report.
- [ ] Confirm whether the catalog should remain in the public repository or be downloaded
  from the official release under the source dataset terms.

## Presentation

- [ ] Record a short end-to-end demo covering Browsing and Intent Override.
- [ ] Upload the video publicly to YouTube and add its URL to Devpost.
- [ ] Prepare one architecture slide and one public-vs-shadow results slide.
- [ ] Rehearse an explanation of why constraint coverage precedes semantic relevance.
- [ ] Verify that all third-party assets and trademarks used in the video are permitted.
