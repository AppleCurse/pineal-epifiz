# Private Instagram profile handling

## Correct behavior

A private profile may still expose a small amount of page-visible profile metadata. The scraper preserves only values actually present in the returned page/payload (display name, bio, counts, explicit website, and URLs written in the bio). It does not invent posts or follow those links.

The task pipeline returns `partially_completed` with `telemetry.result_kind = public_profile_metadata_only`. It intentionally skips personality/affect inference, username-based account discovery, related-profile traversal, and post-content analysis. The cross-profile correlator also rejects private Instagram targets as defense in depth.

## Previous failure chain

1. `InstagramGhostScraper._parse_real_profile` raised as soon as `is_private` and no readable posts were seen.
2. That discarded any profile fields already parsed from public page metadata.
3. The confidence gate then treated content confidence as an all-or-nothing task gate, so downstream code did not receive an honest metadata-only result.
4. Downstream OSINT/deep-profile stages can otherwise expand usernames into discovered profile URLs, which is not an appropriate fallback for a private target.

## Verification boundaries

Offline tests should assert that metadata survives parsing, no post is fabricated, private targets short-circuit the executor, and cross-profile correlation returns no identity links. Live Instagram behavior is not asserted: page markup, session requirements, rate limits, and available public fields are controlled by Instagram and can change.
