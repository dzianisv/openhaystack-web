# PRD — Mobile access to openhaystack-web tags

Status: draft. Owner: repo author (single maintainer). Supersedes the earlier Mac-backend draft, which is void.
Technical detail (formats, protocol steps, crypto, build config) belongs in `docs/LLD.md`. This document specifies none of it.

## 1. Summary

`openhaystack-web` locates home-made OpenHaystack BLE tags (ESP32/nRF firmware in `firmware/`) through Apple's Find My network using `FindMy` 0.10.2. Everything is desktop-only, but the question the owner actually asks — "where is my car?" — is asked away from the desk, on a phone. The path to a standalone phone app is now open: Apple's ADI libraries may be **downloaded at runtime from Apple's CDN and never bundled or redistributed**, which is exactly how OpenTagViewer runs Find My on Android with no server and no Mac. Android is priority 1, iOS priority 2. The uncomfortable part of this document is §6: `tools/export_opentagviewer.py` shipped this session and already puts the owner's real tags on Android through an actively-maintained MIT app, so the honest question is not "how do we build our app" but "should we build one at all".

| | |
|---|---|
| **Problem** | Tag locations are viewable only from a desktop. The owner needs them on a phone, standalone, with no server and no Mac in the loop. |
| **Users** | One: the self-hosting owner-operator (the repo author). |
| **Solution** | Recommended: ship and maintain the export bridge to OpenTagViewer (Option A), contribute upstream, and hold our own app behind explicit trigger conditions (§6). |
| **Non-goals** | An App Store iOS release (impossible, §4/§11); bundling or redistributing Apple's binaries; a hosted service; a single universal iOS+Android codebase (not achievable in a form worth paying for, §6). |

## 2. Background — why desktop-only is the wrong shape

The job to be done is one sentence: *"Where is my car / my backpack, right now, checked from my phone."*

| What the desktop gives | What the job needs |
|---|---|
| A map on a machine at home | A map in a pocket |
| A Python process the owner starts | Something that works when the laptop is shut |
| A CLI that prints JSON | A glanceable answer in seconds |
| BLE scanning bound to the desk | BLE scanning while walking around the room the tag is in |

Every desktop entry point is correct software aimed at the wrong moment. A phone is not a nicer front end here; it is the only front end that is present when the question is asked.

The previously-considered "self-hosted backend on a Mac + thin mobile client" design is rejected outright: a laptop backend is unreachable exactly when the owner is out of the house, and the design forced an always-on Mac as the price of entry. Standalone-on-phone removes the Mac from the loop entirely.

## 3. Current state — what already works

| Component | Function | Status |
|---|---|---|
| `app.py` | eel desktop app, Leaflet map | Works, desktop only |
| `backend/app.py` | Sanic HTTP server | Works, desktop only |
| `tools/locations.py` | CLI, prints locations | Works, desktop only |
| `tools/scan.py` | Local BLE scan; finds tags in radio range with **no Apple account at all** | Works, desktop only |
| `tools/findmy_login.py` | One-time interactive Apple ID login | Works |
| `tools/export_opentagviewer.py` | Converts `trackers.json` into an OpenTagViewer import bundle (format 0.0.3, `custom_rolling_key_accessory` records), built by OpenTagViewer's own exporter rather than reimplemented | **Shipped this session, commit `dc82451`. Verified on both real tags.** |
| Test suite | 74 tests | Passing |

**Live account state.** Signed in as `thoughtful.fennec@gmail.com`.

| Tag | Result | Meaning |
|---|---|---|
| 🐼 Den | 8 reports in the last week | The full pipeline works end to end against real Apple infrastructure |
| 🚗 minicooper | Zero reports | Out of network range, or dead battery. **Cannot be distinguished from report data alone.** Must be a first-class UI state, never an empty map. |

**The fact that reframes this PRD:** with `tools/export_opentagviewer.py`, the owner can run their tags on Android **today, with zero app development**. Any proposal to write an app must beat that baseline, not merely be better than the desktop status quo.

## 4. Constraints

### Hard — not negotiable, not engineerable around

| # | Constraint | Consequence |
|---|---|---|
| H-1 | Apple's ADI libraries may be **downloaded at runtime from Apple's CDN only**. Never bundled, never redistributed, never checked into the repo or an artifact we publish. | Rules out any distribution channel that forbids downloading executable code. |
| H-2 | **App Store distribution of an anisette-capable iOS app is impossible**, on four independent and individually sufficient grounds: Guideline 2.5.2 (downloading and executing code); Guideline 2.5.1 (private API, if AuthKit is used instead); no licence to redistribute Apple's binaries; AnisetteKit's AGPLv3 plus its explicit "App Store Distribution Prohibited". | iOS is sideload-only, permanently. Not a scheduling problem. |
| H-3 | An Android ELF cannot be `dlopen`ed on iOS — dyld requires Mach-O — and iOS mandatory code signing refuses downloaded dylibs regardless. | The Android ADI approach does not port. iOS needs emulation (SideStore 0.7.0-alpha / `mahee96/AnisetteKit`, Unicorn-TCI) or nothing. |
| H-4 | iOS CoreBluetooth does not deliver Find My manufacturer data to third-party apps, and never exposes the peripheral MAC. Evidence: seemoo-lab's own AirGuard-iOS reduces AirTag detection to the heuristic "connectable, nameless, carrying no manufacturer data". | "Which of my tags is in this room" cannot work on iOS the way it works on Android — unless the firmware also advertises a custom 128-bit service UUID, since service data **is** delivered on iOS. See R-7. |
| H-5 | Tracker private keys are the permanent decryption capability for a tag. A leaked key is not revocable without reflashing. | Governs every storage and transport decision in §10. |

### Soft — real, but tradeable

| # | Constraint | Consequence |
|---|---|---|
| S-1 | Upstream breaks roughly every **6-8 weeks** — ~14 events in 24 months. Most recent: Apple's GSA edge 503-ing any request whose `X-MMe-Client-Info` names `com.apple.dt.Xcode` (Sept 2026; fixed in FindMy.py 0.10.2 and OpenTagViewer 1.1.0). | Breakage is the normal operating condition, not an incident. Whatever we own, we must be willing to fix on that cadence. |
| S-2 | `macless-haystack` is still broken by the Sept 2026 GSA change and should be treated as unmaintained. | Not a viable reference or dependency. |
| S-3 | Notably **not** broken: the Apple Music APK URL and the ADI symbol names — byte-stable since 2025-04-15, no re-obfuscation ever recorded. | The ADI-download mechanism is the *stable* part of this stack. The GSA transport layer is the fragile part. |
| S-4 | Single maintainer on our side, and a single maintainer upstream (OpenTagViewer, 398 stars). | Bus factor 1 on both sides of any dependency. |
| S-5 | OpenTagViewer's APK is 103 MB (universal, 2 ABIs); Chaquopy alone is 27.5 MB for arm64. A single-ABI build is far smaller. | Size is a fixable annoyance, not a blocker. |

## 5. Users

**Primary, and realistically the only one for v1 — the self-hosting owner-operator.**

| | |
|---|---|
| Who | The repo author. Owns the tags, flashed the firmware, holds the Apple ID. |
| Comfortable with | Terminal, Python, sideloading an APK, editing JSON, reflashing an ESP32. |
| Wants | To open a phone and see where the car is. |
| Will not tolerate | A Mac in the loop; a silent failure with no stated cause. |

**Out of scope for v1:** a second user, a family member with read access, or anyone who cannot sideload. Anything involving a second Apple ID also inherits R-4 and R-5.

## 6. Options — and a recommendation

This is the heart of the document. The baseline to beat is "the exporter already works".

### The options

| | **A — Use OpenTagViewer, contribute upstream** | **B — Fork its native ADI, build our own Flutter UI** | **C — Rust core via flutter_rust_bridge** |
|---|---|---|---|
| App code we own | None | Full Android app | Full app + shared core |
| Time to owner value | **Zero — already delivered** | Months | Longer, with unfinished prerequisites |
| UX control | None | Full | Full |
| iOS story | Same as upstream's | **A rewrite, not a port** — Chaquopy has no iOS support (maintainer-confirmed) | Shared core in theory |
| Known blockers | Single-maintainer dependency; 103 MB APK; our repo becomes a key-conversion utility | Flutter+Chaquopy Gradle gotcha (chaquopy#1289); **no production open-source precedent** | Repo dormant **22 months**; still ships the client-info string Apple now blocks; **zero Find My report-fetching code** — GSA/SRP done, but mobileme delegate, searchPartyToken and P-224 decrypt all absent |
| Who absorbs the 6-8 week breakage | Upstream (129 commits in Sept 2026, HEAD 2026-09-19, releases through v1.1.1, runs weekly `check-adi-libraries.yml` and daily `check-gsa-edge.yml`) | **Us** | **Us, with no upstream at all** |

### On the "universal codebase" idea

State it plainly: **a single codebase across iOS and Android is not achievable here in a form worth paying for.**

| Layer | Portable? |
|---|---|
| UI | Yes |
| P-224 / X9.63 / AES-GCM report decryption | Yes |
| Anisette generation | **No** — native ELF on Android, Unicorn-TCI emulation on iOS |
| GSA transport / account handling | **No** — diverges with the anisette path |
| BLE | **No** — H-4 makes the iOS feature a different feature |

So the shared surface is the easy half. The hard half diverges no matter which framework is chosen. Option C's appeal is precisely this shared core, and Option C is the option whose core does not exist yet.

### Recommendation: **Option A now, with explicit triggers to revisit**

Reasons, in order of weight:

1. **It is already delivered and verified** on the owner's two real tags (commit `dc82451`). Options B and C are proposals; A is a fact.
2. **It moves the 6-8 week breakage burden upstream.** OpenTagViewer is the only project in this ecosystem running drift monitors — `check-adi-libraries.yml` weekly, `check-gsa-edge.yml` daily — and it shipped the Sept 2026 GSA fix in v1.1.0 while macless-haystack remains broken (S-2). We would be replacing a maintainer who is demonstrably faster at this than we will be part-time.
3. **Its "inactive" repostatus badge is stale.** 129 commits in Sept 2026, HEAD 2026-09-19. Judge by commits, not badges.
4. **It already supports self-generated OpenHaystack tags** (`FixedRollingKeyPairAccessory`). No upstream feature work is needed to serve our case.
5. Options B and C both require us to own the ADI download, GSA transport, and breakage response — the three hardest parts — to gain UI control, which is the part the owner has not complained about.

**Honest weaknesses of Option A — stated, not buried:**

- Bus factor 1 upstream (S-4). If that maintainer stops, we inherit everything with no warning and no prepared position.
- Zero UX control. The no-reports state (§3) is rendered however upstream renders it; we cannot fix it ourselves.
- 103 MB APK on the owner's phone (S-5).
- Our repo's role shrinks to "key-conversion utility plus desktop tools". That is a smaller project than the one the owner may want to be working on. It is still the right call.
- The export bundle contains private keys in transit between two systems (see SEC-3).

**Triggers that reopen the decision — any one is sufficient:**

| Trigger | Move to |
|---|---|
| OpenTagViewer goes >6 months with no commits *and* is broken by an upstream change | B |
| Upstream refuses a contribution we need for our tag format | B |
| The owner finds the UX materially blocking after 30 days of real use | B |
| `SideStore/apple-private-apis` gains mobileme-delegate + searchPartyToken + P-224 decrypt **and** resumes commits | Re-evaluate C |

Until a trigger fires, our app code stays at zero lines. §7-§9 below specify the product we would want in a B/C world and the acceptance bar upstream must meet in an A world — they are the same requirements either way, which is deliberate: it makes upstream's suitability continuously measurable.

### Architecture under the recommendation

```
 ┌────────────────────────────────────────────────────────────────────┐
 │  Desktop (this repo — Python)                                      │
 │                                                                    │
 │   trackers.json ──► tools/export_opentagviewer.py ──► import       │
 │        │             (format 0.0.3, built by OTV's own exporter)   │
 │        │                                            bundle (KEYS!) │
 │        ▼                                                  │        │
 │   app.py / backend/app.py / tools/locations.py            │        │
 │   tools/scan.py (BLE, no Apple account)                   │        │
 └───────────────────────────────────────────────────────────┼────────┘
                        one-time, out-of-band, delete after  │
                                                             ▼
 ┌────────────────────────────────────────────────────────────────────┐
 │  Android phone — OpenTagViewer (MIT, standalone)                   │
 │                                                                    │
 │   ┌──────────────┐   Range-GET ~2.6 MB of 142 MB APK               │
 │   │ adi.cpp (C++)│◄──────────────── apps.mzstatic.com (Apple CDN)  │
 │   │ + anisette/  │   downloaded at runtime, never bundled (H-1)    │
 │   └──────┬───────┘                                                 │
 │          │ anisette headers                                        │
 │   ┌──────▼──────────────┐                                          │
 │   │ FindMy.py (Chaquopy)│───► Apple GSA / Find My ──► reports      │
 │   │  protocol layer only│                                          │
 │   └─────────────────────┘                                          │
 │                                                                    │
 │   BLE scan ◄────── tag advertisement ◄────── ESP32/nRF tag         │
 │   (no Apple involvement at all)                                    │
 └────────────────────────────────────────────────────────────────────┘

 iOS: sideload-only, permanently (H-2). Anisette via emulation, not ELF (H-3).
      BLE proximity not achievable as on Android (H-4).
```

## 7. User stories

Acceptance criteria are the bar upstream must meet (Option A) or we must build (B/C).

### P0

**US-1 — See all tags on one map.**
- Every configured tag appears in one view with its label, including emoji ("🐼 Den").
- Tags with no known location are listed but not placed on the map.
- Previously-fetched positions render before any network call completes.

**US-2 — See one tag's history over a selectable window.**
- Window selectable from at least 1h / 24h / 7d.
- Reports ordered by time, shown as a path plus individual points; timestamp available per point.
- Zero reports in the window is stated explicitly, not rendered as an empty map.

**US-3 — Know how stale a report is.**
- Relative age ("4 min ago", "2 days ago") shown next to every position.
- Freshness graded with a non-colour-only cue.
- Absolute timestamp with timezone available on demand.

**US-4 — Know when a tag has NO recent reports.** (The verified "🚗 minicooper" case.)
- Explicit "no reports in <window>" state in the list, reachable without opening a detail screen.
- Last known position shown if one exists outside the window, clearly marked as older than the window.
- Plausible causes stated — out of network range, or dead battery — **without asserting which**. Must never claim the tag is "at" its last location.

**US-5 — Onboarding and Apple sign-in.**
- The owner imports their tags from an export bundle and signs in to Apple on the phone, with no Mac and no server involved.
- 2FA is handled; Trusted-Device 2FA must work (the owner's account offers it).
- The bundle is deleted from both machines after a successful import, and the app says so.
- Sign-in failure states the cause: wrong credentials, 2FA failed, account limit reached, or Apple rejected the request.

**US-6 — Recovery when Apple breaks upstream.**
- The app distinguishes "network down", "Apple session invalid", "Apple rejected the request" and "app version too old for current Apple behaviour", with a different message for each.
- Previously-fetched data stays viewable, marked stale, throughout.
- On the "too old" class, the message names the fix: update the app. (Precedent: the Sept 2026 GSA change, fixed in FindMy.py 0.10.2 / OpenTagViewer 1.1.0.)

### P1

**US-7 — Find a tag in the room by BLE proximity (Android).**
- Detects a tag in radio range with the device offline and no Apple account, mirroring verified `tools/scan.py` behaviour.
- Continuous coarse proximity from signal strength, labelled approximate; direction not claimed.
- Denied Bluetooth/location permission produces an actionable prompt, not silence.
- **iOS: not achievable in this form (H-4).** Do not ship a degraded lookalike on iOS; see R-7.

**US-8 — Refresh on demand and know what happened.**
- Manual refresh from map and list; last successful fetch time always visible; a failed refresh preserves existing data and states the reason.

**US-9 — Keep the phone's tag list in step with `trackers.json`.**
- Re-export and re-import updates tags without hand-editing on the phone.
- Re-import does not duplicate existing tags.

### P2

**US-10 — Notify when a silent tag reappears.** Opt-in per tag; exactly one notification per silence episode.
**US-11 — iOS sideload build.** Priority 2. Blocked on the risk assessment in R-6; not started until Android is stable in daily use.
**US-12 — Second user / shared read access.** Out of scope for v1 (§5, §12).

## 8. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | The system shall locate tags from a phone with no desktop, server, or Mac running. |
| FR-2 | The system shall obtain ADI libraries by runtime download from Apple's CDN only, and shall never bundle or redistribute them. |
| FR-3 | The export tool shall convert `trackers.json` into an import bundle consumable by the target Android app. *(Delivered, `dc82451`.)* |
| FR-4 | The export tool shall produce its bundle using the target app's own exporter rather than a reimplementation of the format. *(Delivered.)* |
| FR-5 | The export tool shall write the bundle only to a path the owner specifies, and shall warn that it contains private keys. |
| FR-6 | The phone app shall render all tags on one map with labels. |
| FR-7 | The phone app shall render per-tag history for a window of at least 1h / 24h / 7d. |
| FR-8 | The phone app shall show a relative age and a non-colour-only freshness cue for every position. |
| FR-9 | The phone app shall render an explicit zero-reports state per tag, naming both plausible causes without asserting either. |
| FR-10 | The phone app shall render previously-fetched data before completing any network call. |
| FR-11 | The phone app shall perform Apple sign-in on-device, including Trusted-Device 2FA. |
| FR-12 | The phone app shall surface the failure classes in US-6 as distinct, actionable messages. |
| FR-13 | The phone app shall scan for tag advertisements locally on Android, offline, with no Apple account. |
| FR-14 | The phone app shall present BLE proximity as coarse and approximate, and shall not claim direction. |
| FR-15 | The phone app shall never transmit tracker private keys off the device. |
| FR-16 | The phone app shall offer manual refresh and display the last successful fetch time. |
| FR-17 | Re-importing an updated bundle shall update tags without creating duplicates. |
| FR-18 | The project shall document, in `docs/LLD.md`, how to verify that a candidate upstream release still satisfies FR-6..FR-14. |
| FR-19 | The project shall track upstream releases and record, per breakage event, the date and the version that fixed it. |

## 9. Non-functional requirements

| Area | Requirement |
|---|---|
| Availability | No dependency on any machine the owner must keep awake. The phone is the whole system. |
| Performance | Previously-fetched data renders in **< 1 s** from cold start. A fresh fetch completes in **< 10 s** or fails with a stated reason inside that budget. |
| Reliability | Upstream breakage every 6-8 weeks is the expected condition (S-1). Every failure degrades to stale-marked cached data, never a blank screen. |
| Battery | No background location or background BLE in v1. BLE scanning runs only while its screen is foregrounded. |
| Offline | Read-only use offline: cached positions and history render, every value marked stale. |
| Size | APK size is tracked. 103 MB universal is acceptable but not good; a single-ABI build is the remedy if it becomes a complaint (S-5). |
| Accessibility | Screen-reader labels on markers and rows; freshness never colour-only; system text scaling respected. |
| Maintainability | Any component we own must be fixable by one part-time maintainer within one breakage cycle. This is the main argument against Options B and C. |
| Licensing | OpenTagViewer is MIT (© 2025 Shane B.) — attribution preserved in any reuse. AnisetteKit is AGPLv3 with App Store distribution prohibited; its terms must be honoured if iOS work ever starts. |

## 10. Security & privacy

| ID | Requirement | Rationale |
|---|---|---|
| SEC-1 | Tracker private keys live on the phone in v1. They must be stored in platform-protected app storage and never transmitted off-device. | Standalone means the keys must be there. A key leak is permanent (H-5). |
| SEC-2 | No component shall log a private key. | Logs are the most commonly leaked artifact. |
| SEC-3 | **The export bundle contains private keys.** It must be transferred out of band, must not be sent through cloud storage, chat, or email, and must be deleted from both the desktop and the phone immediately after a successful import. Tooling and docs must say so at the point of use. | A file sitting in `~/Downloads` and in a Files app is two permanent copies of a non-revocable secret. |
| SEC-4 | The Apple ID password is stored **in plaintext** by FindMy.py in its state file. We inherit this and cannot fix it. It must stay on a device only the owner controls, must never be exported, and must never be included in any backup this project creates. | Inherited upstream design. Containment is the only available control. |
| SEC-5 | Location history is personal data. No third-party analytics, ad, or crash-reporting SDK in anything we ship. No telemetry. | Any such SDK converts a private location tool into a shared one. |
| SEC-6 | ADI libraries are downloaded from Apple's CDN over TLS with validation intact. No "accept any certificate" toggle anywhere. | The downloaded artifact is executed. A MITM here is arbitrary code execution. |
| SEC-7 | Losing the phone means losing the keys and the Apple session. The recovery procedure — remote wipe, Apple password change, reflash tags if the device is unrecoverable — must be documented. | There is no revocation for a tag key; reflashing is the only remedy. |
| SEC-8 | Map tiles are fetched from a third party, which learns the owner's viewport. Document it; do not hide it. | Honest disclosure of a leak we are not fixing in v1. |

## 11. Platform matrix

| Capability | Android | iOS (sideload) | iOS (App Store) |
|---|---|---|---|
| Runtime ADI download from Apple CDN | Yes — native C++ (`adi.cpp`), Range-GET ~2.6 MB of a 142 MB APK | N/A — ELF cannot be `dlopen`ed (H-3) | **Impossible** (H-2) |
| Anisette generation | Native ELF | Emulation only — SideStore 0.7.0-alpha (2026-09-15), `mahee96/AnisetteKit`, Unicorn-TCI | **Impossible** |
| Fetch Find My reports | Yes — verified in production upstream | Only if the emulation path holds | **Impossible** |
| Apple sign-in incl. 2FA | Yes | Presumed yes via the same path — unverified by us | **Impossible** |
| Map, history, staleness, no-reports state | Yes | Yes | N/A |
| BLE proximity to own tags | Yes — manufacturer data and MAC available | **No** — CoreBluetooth withholds Find My manufacturer data and never exposes the MAC (H-4) | **No** |
| BLE proximity *if firmware adds a custom 128-bit service UUID* | Yes | **Yes** — service data is delivered on iOS | N/A |
| Distribution | Sideload APK | Sideload only, permanently | **Ineligible on four independent grounds** (H-2) |
| Maturity of the path | Production: 398 stars, releases to v1.1.1, HEAD 2026-09-19 | **High risk**: repo 5 weeks old, 5 stars, one maintainer, self-contradictory licence metadata | — |

## 12. Out of scope

| Excluded | Why |
|---|---|
| An App Store iOS release | Impossible on four independent grounds (H-2). Not a roadmap item at any date. |
| Bundling or redistributing Apple's binaries | H-1. |
| A self-hosted or Mac-resident backend | Rejected: unreachable exactly when needed; forces always-on Apple hardware. |
| A hosted, multi-tenant service | Personal tool. Hosting others' Apple sessions is a liability we will not take. |
| A single universal iOS+Android codebase | Not achievable in a form worth paying for (§6). |
| Background geofencing / background location | Battery and permission cost disproportionate to v1. |
| Sharing tags with other users | US-12, deferred. |
| Firmware changes | Out of scope **except** the service-UUID decision in R-7, which is a decision to record now, not work to do now. |
| Replacing FindMy.py | Accepted as the upstream protocol layer, weaknesses included. |
| Depending on `macless-haystack` | Still broken by the Sept 2026 GSA change; treat as unmaintained (S-2). |

## 13. Success metrics

Personal tool. No growth or business metrics — they would be fabricated.

| Metric | Target | How measured |
|---|---|---|
| Time to locate a tag from cold app start | < 15 s | Stopwatch, cold start, 5 repetitions |
| Cached render on launch | < 1 s | First frame showing markers |
| Owner locates a tag from the phone with **no desktop running** | Works | Quit every desktop process, then use the phone |
| Zero-reports case renders as an explicit state | 100% of tested tags | Reproduce the verified "🚗 minicooper" case |
| Blank or unexplained screens on any failure class | **Zero** | Airplane mode; invalidated session; forced Apple rejection |
| Private keys found in any off-device location | **Zero** | Inspect export paths and captured traffic |
| Export bundles still present on disk 24h after import | **Zero** | Filesystem check on both devices (SEC-3) |
| Days of unattended operation before manual intervention | Tracked, not targeted — the real Apple session lifetime is currently unknown | Log the date of every forced re-login |
| Breakage recovery time | Within one upstream release cycle | Record date broken / date fixed / fixing version (FR-19) |
| Lines of app code we maintain | **0** while Option A holds | `git` |

## 14. Milestones

### Phase 0 — Export bridge — **DELIVERED**
Commit `dc82451`. `tools/export_opentagviewer.py` converts `trackers.json` to an OpenTagViewer import bundle (format 0.0.3, `custom_rolling_key_accessory`), built by OpenTagViewer's own exporter rather than reimplemented.
Definition of done — **met**: FR-3, FR-4 implemented; verified on the owner's two real tags; 74 tests pass.

### Phase 1 — Android in daily use (Option A)
Scope: owner installs OpenTagViewer, imports the bundle, signs in to Apple, uses it as the primary way to find tags for 30 days.
Definition of done:
- FR-1, FR-6..FR-12, FR-16 satisfied **by upstream**, each verified by hand against §7 acceptance criteria.
- The zero-reports case observed and judged acceptable, or filed upstream.
- Export bundles deleted from both devices (SEC-3); verified.
- A written verdict at day 30: does Option A hold, or has a §6 trigger fired?

### Phase 2 — Upstream contribution and monitoring
Scope: file or fix whatever Phase 1 exposed; keep the exporter in step with upstream's format; track releases.
Definition of done:
- FR-18 (upstream acceptance checklist in `docs/LLD.md`) and FR-19 (breakage log) in place.
- The exporter is verified against the newest upstream release, and that verification is repeatable.

### Phase 3 — Android BLE proximity verdict
Scope: determine whether upstream's BLE behaviour meets US-7, or whether `tools/scan.py`'s capability is missing on Android.
Definition of done: a tag physically present in the room is detected by the phone, offline, with no Apple account — or a filed upstream issue explaining why not.

### Phase 4 — iOS (priority 2, gated)
Not started until Phase 1 returns a positive verdict and Android is stable in daily use.
Definition of done for the *assessment* (not the build): a written go/no-go on `mahee96/AnisetteKit`, covering its age (5 weeks), maintainer count (1), star count (5), and self-contradictory licence metadata; plus an explicit decision on R-7. A "no-go" is a perfectly good outcome.

### Phase 5 — Build our own app
**Not scheduled.** Entered only when a §6 trigger fires. Scope would be Option B; Option C only if `SideStore/apple-private-apis` both resumes commits and gains the missing Find My layer.

## 15. Risks & open questions

| # | Risk / question | Impact | Mitigation |
|---|---|---|---|
| R-1 | **Single-maintainer upstream.** OpenTagViewer has 398 stars and one maintainer (S-4). | If they stop, we inherit ADI, GSA and breakage response with no notice. | Track commit cadence as part of FR-19. Keep the exporter independent of upstream internals where possible. The §6 triggers exist precisely for this. |
| R-2 | **Breakage every 6-8 weeks** (~14 events in 24 months, S-1). | The app stops working with no warning, repeatedly and forever. | Option A puts the fix upstream, where the drift monitors already live (weekly `check-adi-libraries.yml`, daily `check-gsa-edge.yml`). Surface the "app too old" failure class (US-6) so the owner knows the remedy is "update", not "debug". |
| R-3 | The ADI download mechanism itself breaks. | Total outage; no local workaround. | Low probability relative to GSA: the APK URL and ADI symbol names have been byte-stable since 2025-04-15 with **no re-obfuscation ever recorded** (S-3). Watch, do not pre-engineer. |
| R-4 | **"Account limit reached" on `com.apple.mobileme`** — hits Apple IDs never used on genuine Apple hardware. The owner already hit this on a *different* Apple ID and resolved it by switching accounts. | New or second accounts can be blocked outright. | The only remedy confirmed across four reporters: sign in once on a genuine iPhone/iPad/Mac. Any second user must be warned before they start. Also treat Apple-side rate limiting as possible — frequency unknown, see Q-2. |
| R-5 | **SMS-only 2FA defect** (OpenTagViewer#236): `au=secondaryAuth` loops at `REQUIRE_2FA`. | Sign-in impossible on affected accounts. | The owner's current account offers **Trusted-Device 2FA**, so this most likely does not apply to them. It remains a hard blocker for any second user on an SMS-only account, and must be checked before onboarding one. |
| R-6 | **iOS sideload path is immature.** `mahee96/AnisetteKit` is 5 weeks old, 5 stars, one maintainer, with self-contradictory licence metadata; SideStore 0.7.0-alpha is dated 2026-09-15. | iOS may never ship, or may ship and then break permanently. | Treat as high risk. Phase 4 delivers an assessment, not a build. "No-go" is an acceptable and likely outcome. iOS is priority 2 for a reason. |
| R-7 | **iOS BLE proximity is impossible as designed** (H-4), *unless* the tag firmware also advertises a custom 128-bit service UUID — service data **is** delivered on iOS. | Deciding late means reflashing every tag by hand. | **This is cheap now and expensive later.** Record the decision during Phase 1, not Phase 4, even though the firmware work itself is out of scope. Open question: whether adding a service UUID affects Find My network acceptance of the advertisement — unknown, see Q-3. |
| R-8 | **APK size** — 103 MB universal, 2 ABIs; Chaquopy is 27.5 MB for arm64 alone (S-5). | Annoying on a phone; not a blocker. | A single-ABI build is far smaller. Raise upstream only if the owner actually complains. |
| R-9 | **Private keys on the phone** (SEC-1) and **in the export bundle** (SEC-3). | A lost phone or a stray bundle is a permanent compromise of those tags; only reflashing fixes it. | Delete bundles after import and verify (§13). Document the lost-phone procedure (SEC-7). |
| R-10 | **Plaintext Apple ID password** in FindMy.py's state file (SEC-4). | Read access to the device or its backups yields the Apple ID. | Inherited; cannot be fixed by us. Never export it; exclude it from any backup this project creates. |
| R-11 | Our repo's role shrinks to a key-conversion utility under Option A. | Demotivating; and if upstream dies we have built no relevant muscle. | Accept it. Phase 2's contribution work is the hedge: it keeps us inside the upstream codebase. |
| R-12 | Zero-report cause is genuinely undeterminable from report data (out of range vs. dead battery). | The UI must not claim a cause. | FR-9. Do not add a battery indicator unless the firmware actually reports one — currently unknown, see Q-4. |

### Open questions

| # | Question | Why it is open |
|---|---|---|
| Q-1 | What is the real Apple session lifetime before a manual re-login is required? | Never measured. Phase 1 measures it (§13). |
| Q-2 | Does Apple rate-limit report fetching, and at what frequency? | No data. Do not assume a safe polling interval until measured. |
| Q-3 | Does adding a custom 128-bit service UUID to the tag advertisement affect Find My network acceptance? | Unknown. Blocks a clean answer to R-7. |
| Q-4 | Does the ESP32/nRF firmware expose battery state at all? | Unknown. Determines whether the zero-report state can ever be disambiguated. |
| Q-5 | Does upstream's BLE implementation match `tools/scan.py`'s verified capability? | Unverified. Phase 3 answers it. |
| Q-6 | Does upstream's zero-reports UI meet FR-9, or must we file an issue? | Unverified until Phase 1. |

---

Technical detail — bundle format, protocol steps, crypto, build configuration, upstream acceptance checklist — belongs in `docs/LLD.md`.
