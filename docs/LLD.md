# Low-Level Design — standalone mobile tag viewer

Target: a phone app that locates our OpenHaystack tags with **no server, no Mac, no companion process**. Android first, iOS second.

Product rationale, users and success criteria: [`docs/PRD.md`](./PRD.md). This document is only *how*.

Reference implementation read for this design: **OpenTagViewer** (MIT, © 2025 Shane B., `github.com/parawanderer/OpenTagViewer`), shallow clone at `/tmp/otv`, HEAD `335b258` (2026-09-19, v1.1.1). It already ships everything hard about this problem on Android. The "inactive" badge in its README is stale — 129 commits in September 2026.

---

## 1. Scope & goals

| In scope | Out of scope |
|---|---|
| Runtime ADI/anisette on the phone (download from Apple's CDN, never bundle) | Running Apple binaries on our own servers |
| Android app that fetches and decrypts reports on-device | Any backend, any Mac, any relay |
| Our tracker keys reaching the phone (`tools/export_opentagviewer.py`, shipped) | Re-implementing the export bundle format by hand |
| BLE proximity scan on Android | BLE identification of our tags on **stock** iOS firmware (impossible, §7) |
| iOS as a separate sideloaded Swift app | iOS App Store distribution (impossible, §7) |
| Upstream-drift CI so Apple's next change is detected, not discovered | Guaranteeing Apple never breaks it |

Two decisions frame everything below:

1. **Apple's ADI libraries are acceptable when downloaded at runtime from Apple's own CDN, never redistributed.** This is the same position every public anisette server occupies.
2. **Android and iOS are different products, not one codebase.** iOS cannot `dlopen` an Android ELF and cannot see our tags over BLE. Pretending otherwise produces a port that does not work.

---

## 2. Context

```
 ┌──────────────────────────── the phone (no server anywhere) ─────────────────────────────┐
 │                                                                                          │
 │  imported bundle ──► tag private keys (28-byte P-224 scalars)  ◄── LIVE ONLY HERE        │
 │  Apple ID + password ──► FindMy.py account state (plaintext pw, see §11)                 │
 │                                                                                          │
 │  ┌────────────┐   ┌─────────────────┐   ┌──────────────────┐   ┌────────────────────┐    │
 │  │ UI         │   │ protocol layer  │   │ anisette (native)│   │ BLE scanner        │    │
 │  │ list/map   │──►│ FindMy.py       │──►│ libCoreADI.so    │   │ 0x004C / type 0x12 │    │
 │  │ history    │   │ (Chaquopy)      │   │ libstoreservices │   │                    │    │
 │  └────────────┘   └───────┬─────────┘   └────────┬─────────┘   └─────────┬──────────┘    │
 └───────────────────────────┼──────────────────────┼───────────────────────┼───────────────┘
                             │                      │                       │
        ┌────────────────────┼──────────────────────┼───┐                   │ BLE advert
        │                    ▼                      ▼   │                   │ (adv key)
        │  gateway.icloud.com      gsa.apple.com        │          ┌────────▼─────────┐
        │  (encrypted reports)     (Grand Slam auth,    │          │ our nRF5x tags   │
        │                           pinned 2006 root CA)│          └────────┬─────────┘
        └───────────────────────────────────────────────┘                   │ BLE
                             ▲                                              ▼
       apps.mzstatic.com/content/android-apple-music-apk/    ┌──────────────────────────┐
       applemusic.apk  ── HTTP Range, ~11 MB of 142 MB ───►  │ passer-by iPhones        │
       (one-time ADI library download)                       │ → encrypted reports      │
                                                             └──────────────────────────┘
```

| Secret | Lives | Leaves the phone? |
|---|---|---|
| tag `private_key` (28 bytes) | phone app storage | never — reports are decrypted locally |
| tag `advertisement_key` | phone + broadcast by the tag itself | over the air, by design |
| Apple ID password | phone, in FindMy.py's state JSON, **plaintext** | to `gsa.apple.com` at login only |
| anisette/ADI provisioning state | phone `filesDir` | machine-id + OTP headers per request |

There is no shared component, no account on our side, and nothing to operate.

---

## 3. The anisette/ADI pipeline

This is the crux of the whole product. Apple's Grand Slam endpoint refuses a login without valid `X-Apple-I-MD` (one-time password) and `X-Apple-I-MD-M` (machine identifier) headers, which only Apple's ADI code can produce. OpenTagViewer runs that code on the phone. The steps below cite its real files.

```
 (1) manifest             app/src/main/assets/adi-libraries.json
     pins APK 4.9.6.1447, 142,139,820 bytes, ETag "21820f71…", per-ABI sha256
                │
 (2) Range fetch          anisette/AdiLibraryFetcher.java
     GET applemusic.apk  Range: bytes=<tail>          → find EOCD ("PK\5\6", 65536+22 window)
     GET Range: <cd>                                  → parse central dir ("PK\1\2", 46-byte hdr)
     GET Range: <member>  ×N                          → only the members we need
     measured: 11 libs, 11.3 MB of 142 MB (7.9%)
                │
 (3) verify + write       anisette/AdiLibraryImporter.java
     sha256 each member against the manifest, inflate, write into filesDir
                │
 (4) sacrificial probe    anisette/TryItElsewhereFirst.java → AppleLibraryProbe →
                          AppleLibraryProbeService (android:process=":adiprobe")
     a throwaway process dlopens the library FIRST and dies in our place
                │
 (5) load-once guard      anisette/NativeLoadGuard.java
     record written with SharedPreferences.commit() BEFORE the call, cleared after
                │
 (6) dlopen closure       cpp/adi.cpp  (RTLD_NOW | RTLD_GLOBAL, absolute paths, bottom-up)
     libc++_shared → libBlocksRuntime → libdispatch → libicu* → libxml2 → libcurl
       → libCoreFoundation → libmediaplatform → libstoreservicescore → libCoreADI
                │
 (7) dlsym obfuscated     anisette/AdiFunction.java  (the ONE place names live)
                │
 (8) provision            anisette/AdiProvisioning.java   → per-request OTP
                │
 (9) headers              anisette/LocalAnisette.java     → FindMy.py's anisette provider
```

### 3a. Why `dlopen`, not a hand-written ELF mapper

`libstoreservicescore.so` has a `DT_NEEDED` closure of 11 libraries, 28.2 MB unpacked (`docs/anisette-native-android.md` §2a). Dadoum's `Provision` keeps only 2 files and needs a manual mapper to do it. `dlopen` follows `DT_NEEDED` for free, and bionic resolves each `DT_NEEDED` against already-loaded libraries **by SONAME**, so opening the closure bottom-up satisfies every dependency without touching the search path. Why: an 8.7 MB extra download is cheaper than owning an ELF loader.

### 3b. The obfuscated entry points

Apple scrambles the exports and **the names differ between APK builds**. `AdiFunction.java` is the single mapping, and it exists so that a failure reads "ADIProvisioningStart is missing from this build" instead of "rsegvyrt87 is missing".

| Apple name | dlsym symbol | Signature (from Dadoum/Provision `lib/provision/adi.d`) |
|---|---|---|
| `ADILoadLibraryWithPath` | `kq56gsgHG6` | `int(const char *path)` |
| `ADISetAndroidID` | `Sph98paBcz` | `int(const char *id, uint len)` |
| `ADISetProvisioningPath` | `nf92ngaK92` | `int(const char *path)` |
| `ADIProvisioningErase` | `p435tmhbla` | `int(ulong dsId)` |
| `ADISynchronize` | `tn46gtiuhw` | `int(ulong, ubyte*, uint, ubyte**, uint*, ubyte**, uint*)` |
| `ADIProvisioningDestroy` | `fy34trz2st` | `int(uint session)` |
| `ADIProvisioningEnd` | `uv5t6nhkui` | `int(uint session, ubyte *ptm, uint, ubyte *tk, uint)` |
| `ADIProvisioningStart` | `rsegvyrt87` | `int(ulong, ubyte*, uint, ubyte**, uint*, uint*)` |
| `ADIGetLoginCode` | `aslgmuibau` | `int(ulong dsId)` |
| `ADIDispose` | `jk24uiwqrg` | `int(void *ptr)` |
| `ADIOTPRequest` | `qi864985u0` | `int(ulong dsId, ubyte **mid, uint *midLen, ubyte **otp, uint *otpLen)` |

`ADIOTPRequest` returns **machine identifier first, then OTP**. Both are `ubyte**`; wiring them backwards compiles, runs, and produces headers Apple rejects. Documented in `AdiFunction.java` and worth repeating here.

`libCoreADI.so` exports only `JNI_OnLoad`, `cvu8io98wun`, `vdfut768ig` — it expects to be loaded by an Android JVM, which is exactly where we are.

### 3c. The three crash defences (all load-bearing, none optional)

| Defence | File | Problem it solves |
|---|---|---|
| Sacrificial probe process | `AppleLibraryProbeService.java`, `android:process=":adiprobe"` | On a Pixel 5 and a Redmi Note 11 Pro+, `dlopen` of Apple's library raised **SIGBUS/BUS_ADRALN inside static initialisers** (OTV issue #232). A signal is not an exception: the `try/catch` fallback never runs, the process just dies. A throwaway process dies instead, its death is reported to the binder, and the app falls back to a remote anisette server without ever showing a crash |
| Load-once guard | `NativeLoadGuard.java` | The record is written **before** the call with `commit()` (not `apply()` — an async write dies with the process and would never record anything). A record still present at next launch means the call never returned. Keyed by app version + ABI + pinned library build, so a fix on either side retries once instead of writing a device off forever |
| Double-load guard | `adi.cpp`, `RTLD_NOLOAD` probes | Loading the same library twice from two threads segfaults (OTV issue #135). Load happens once, behind a lock |

Skeptical note: defence #1 is the interesting one. The obvious design — wrap `dlopen` in `try/catch` and fall back — is *wrong* and OTV shipped it before learning why. Do not re-derive this.

### 3d. Build flags and transport gotchas

| Gotcha | Fix | Where |
|---|---|---|
| Android 15+ requires 16 KB page alignment; NDK r27 does not default to it | `-DCMAKE_SHARED_LINKER_FLAGS=-Wl,-z,max-page-size=16384` | `app/build.gradle.kts:148` |
| SELinux must permit `execute` from `filesDir` | Verified working: `avc: granted { execute }` on Galaxy S25 / Android 16 / targetSdk 35 | `docs/anisette-native-android.md` |
| `gsa.apple.com` chains to the **2006 Apple Root CA**, absent from certifi and the Android trust store | Pin that root explicitly | FindMy.py `findmy/util/tls.py` |
| HTTP 429 from Apple on connection reuse | Do not reuse the connection across provisioning calls | OTV issue #226 |
| Apple 503s any Grand Slam request naming `com.apple.dt.Xcode` | Use the working client-info strings below | §3e |
| `libmediaplatform` needs `makeWorkQueue`, absent from bionic | Hand-written stub, `cpp/stubs/libmediaplatform_handwritten.cpp` (this stub *was* the #232 SIGBUS) | `cpp/stubs/` |

### 3e. Client-info strings that currently work (FindMy.py 0.10.2)

```
findmy/reports/anisette.py:138
  <MacBookPro18,3> <Mac OS X;13.4.1;22F8> <com.apple.AuthKit/1 (com.apple.akd/1.0)>
findmy/reports/account.py:906
  <MacBookPro18,3> <Mac OS X;13.4.1;22F8> <com.apple.AOSKit/282 (com.apple.accountsd/113)>
User-Agent: akd/1.0 CFNetwork/978.0.7 Darwin/18.7.0
```

Residual risk, unfixed: `anisette.py:175-176` still sends `X-Apple-App-Info: com.apple.gs.xcode.auth` and `X-Xcode-Version`. Apple already blocked `com.apple.dt.Xcode` in September 2026. These two headers are the obvious next thing to go. §10's daily probe exists for exactly this.

---

## 4. Component inventory

| Component | Path | Language | Status | Responsibility |
|---|---|---|---|---|
| Tracker validation | `lib/trackers.py` | Python | existing | `validate_tracker_list`, `build_trackers`, `serialize_location` |
| Apple session (desktop) | `lib/findmy_backend.py` | Python | existing | Desktop-only login/state; **not** used by the phone |
| Export tool | `tools/export_opentagviewer.py` | Python | **shipped (`dc82451`)** | `trackers.json` → OpenTagViewer bundle, 0600 |
| BLE scanner (desktop) | `tools/scan.py` | Python | existing | Reference behaviour for the phone's BLE screen |
| Locations CLI | `tools/locations.py` | Python | existing | Desktop lookup; stays as the fallback tool |
| Tag firmware | `firmware/src/ble_stack.c` | C | existing, change proposed | Offline-finding advert; §7c adds a service UUID |
| Format-drift CI | `.github/workflows/otv-format-drift.yml` | YAML | **new** | Detect upstream bundle-format change |
| ADI/GSA drift CI | `.github/workflows/apple-edge.yml` | YAML | **new** | Weekly APK check, daily GSA probe |
| OpenTagViewer app | upstream, `/tmp/otv` | Java/Kotlin/C++/Python | **upstream** | Option A: the whole client |
| Our Android app | `mobile/` | Dart + Kotlin + C++ | **new, Option B** | Option B: our own client |
| Our iOS app | `ios/` | Swift | **new, Option B2** | Separate sideloaded app |

---

## 5. Option A — OpenTagViewer + our exporter (already works)

This is not a strawman. It is the path that is **working today** and it is the recommended starting point.

```
trackers.json ──► tools/export_opentagviewer.py ──► bundle.zip (0600)
                        │  uses upstream opentagviewer_export.bundle.build_export
                        ▼
              OPENTAGVIEWER.yml            version: 0.0.3
              CustomAccessories/<id>.json  {type: custom_rolling_key_accessory,
                                            identifier, name, private_keys: [...]}
                        │  sideload transfer (§8)
                        ▼
              OpenTagViewer import wizard ──► on-device anisette ──► Apple ──► map
```

### 5a. What we own

| We own | We do not own |
|---|---|
| `tools/export_opentagviewer.py` and its tests | The bundle format |
| The `trackers.json` → `AccessoryExport` mapping | The importer, the anisette stack, the UI |
| Detecting upstream format drift | Upstream's release cadence |

The exporter deliberately **calls upstream's writer** rather than reimplementing the layout. Why: the format has details that look right when wrong — `KeyAlignmentRecords` is plural where its siblings are singular, every file is `.plist` even where macOS names it `.record`, and the plists must be XML because the importer reads them with XPath. A hand-rolled copy imports cleanly and silently loses tags.

Upstream sets `package = false` in `python/pyproject.toml`, so it cannot be pip-installed. The tool takes `--exporter-path` or `$OPENHAYSTACK_OTV_EXPORTER` pointing at a clone's `python/` directory.

### 5b. Format-drift CI — `.github/workflows/otv-format-drift.yml`

The version constants we depend on live in upstream's `python/opentagviewer_export/__init__.py`:

```python
EXPORT_FORMAT_VERSION             = "0.0.2"   # base bundle
EXPORT_FORMAT_VERSION_WITH_CUSTOM = "0.0.3"   # bumped when custom accessories are present
CUSTOM_ACCESSORY_TYPE             = "custom_rolling_key_accessory"
CUSTOM_ACCESSORIES_DIR            = "CustomAccessories"
METADATA_FILENAME                 = "OPENTAGVIEWER.yml"
```

Weekly job:

```yaml
name: OpenTagViewer bundle format drift
on:
  schedule: [{ cron: '0 6 * * 1' }]       # Mondays 06:00 UTC
  workflow_dispatch:
jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: git clone --depth 1 https://github.com/parawanderer/OpenTagViewer.git /tmp/otv
      - run: pip install pyyaml
      - name: Assert the constants we depend on
        run: |
          python - <<'PY'
          import sys; sys.path.insert(0, '/tmp/otv/python')
          import opentagviewer_export as e
          expected = {'EXPORT_FORMAT_VERSION_WITH_CUSTOM': '0.0.3',
                      'CUSTOM_ACCESSORY_TYPE': 'custom_rolling_key_accessory',
                      'CUSTOM_ACCESSORIES_DIR': 'CustomAccessories',
                      'METADATA_FILENAME': 'OPENTAGVIEWER.yml'}
          bad = {k: getattr(e, k) for k, v in expected.items() if getattr(e, k, None) != v}
          if bad: print('DRIFT:', bad); sys.exit(1)
          PY
      - name: Round-trip a real export
        run: |
          OPENHAYSTACK_OTV_EXPORTER=/tmp/otv/python \
            .venv/bin/python tools/export_opentagviewer.py tests/data/trackers.sample.json -o /tmp/b.zip
          python -m zipfile -l /tmp/b.zip | grep -q 'CustomAccessories/'
      - name: Open an issue on drift
        if: failure()
        run: gh issue create -t "OpenTagViewer bundle format drifted" -l bug -b "See the failed run."
```

Why a round-trip and not just constants: a constant check catches a rename, a round-trip catches a *semantic* change (a new required field with an old version string). Both are cheap.

### 5c. Honest limits of Option A

- We do not control the UI, so the "no recent reports" explanation (§6f) is whatever upstream shows.
- Our tag names/emoji survive (`name` in the custom accessory), but our colour/icon scheme does not.
- An upstream release can change the import wizard at any time. The drift job is the only warning.
- Key transfer is a file the user moves by hand (§8).

---

## 6. Option B — our own Flutter app (Android)

Build this only if Option A's limits become intolerable. It is several weeks of work to reach parity with something that already works.

### 6a. Layers

```
 ┌───────────────────────────── Dart / Flutter ──────────────────────────────┐
 │ screens ── riverpod providers ── repositories ── drift (SQLite cache)     │
 └───────────────┬──────────────────────────────┬────────────────────────────┘
      MethodChannel                     MethodChannel/EventChannel
 ┌───────────────▼──────────────┐   ┌────────────▼─────────────────────────┐
 │ Kotlin: FindMyBridge          │   │ Kotlin: BleScanner                   │
 │  → Chaquopy → FindMy.py       │   │  → android.bluetooth.le              │
 └───────────────┬──────────────┘   └──────────────────────────────────────┘
      Java anisette classes (ported from OTV, MIT)
 ┌───────────────▼───────────────────────────────────────────────────────────┐
 │ JNI: adi.cpp  → dlopen/dlsym → Apple's libstoreservicescore / libCoreADI  │
 └───────────────────────────────────────────────────────────────────────────┘
```

### 6b. Directory structure

```
mobile/
├── lib/
│   ├── main.dart · app.dart
│   ├── core/            findmy_bridge.dart (MethodChannel), errors.dart (code enum)
│   ├── data/
│   │   ├── models/      tracker.dart, location_report.dart
│   │   ├── db/          app_database.dart (drift)
│   │   └── repos/       tracker_repository.dart
│   └── features/        trackers/ · map/ · history/ · ble/ · onboarding/
├── android/app/src/main/
│   ├── java/…/anisette/ (ported from /tmp/otv, MIT, attribution kept)
│   ├── cpp/adi.cpp + stubs/
│   ├── python/main.py   (Chaquopy entry; FindMy.py protocol calls)
│   └── assets/adi-libraries.json
└── test/ · test/goldens/ · integration_test/
```

### 6c. Flutter ↔ Kotlin ↔ JNI

`NativeAdi.java` is a plain class over `long` handles and `byte[]`:

```java
public static native String open(String path, long[] handleOut);
public static native long   resolve(long handle, String symbol);
public static native int    callWithPath(long function, String directory);
public static native int    setAndroidId(long function, byte[] identifier);
public static native byte[] provisioningStart(...);
public static native int    provisioningEnd(long function, int session, byte[] ptm, byte[] tk);
public static native byte[][] otpRequest(long function, long dispose, long dsId, int[] out);
```

No Android framework types cross that boundary, so the whole anisette stack is portable into any Android app as-is. That is the single biggest reason Option B is feasible at all.

Dart side — one channel, one error taxonomy:

```dart
class FindMyBridge {
  static const _ch = MethodChannel('openhaystack/findmy');

  Future<AnisetteStatus> anisetteStatus();
  Future<void> login({required String appleId, required String password});
  Future<List<TwoFactorMethod>> twoFactorMethods();
  Future<void> submitTwoFactorCode(String code);
  /// Returns the raw `{name: [{lat,lng,accuracy,reported_at}]}` map.
  Future<Map<String, dynamic>> fetchLocations({
    required List<String> ids, required double hours,
  });
}
```

Kotlin implements each by calling into Chaquopy; Python side reuses `lib/trackers.py`'s serialization shape verbatim so the Dart models below match `tools/locations.py` output exactly.

### 6d. Chaquopy

| Item | Value | Why |
|---|---|---|
| Licence | MIT since 12.0.1; current 17.1.0 | No licence blocker |
| iOS | **none**, maintainer-confirmed | Hard stop → §7 |
| `cryptography` | prebuilt wheel, capped at **42.0.8** | Any dep needing >42.0.8 is a hard stop |
| Native deps | Only Chaquopy's prebuilt set | `unicorn` is not in it → stub wheel |
| FindMy.py | Pinned fork `parawanderer/FindMy.py@7969003ca785658369b650f75d9e7ca519566bf6` | Upstream 0.10.2 lacks fixes OTV needs; pin, do not float |

**unicorn stub wheel.** `FindMy >= 0.9` depends on `anisette`, which depends on `unicorn` (a CPU emulator used only for *remote-free local* anisette that we do not use on Android — we have the real ADI). Chaquopy cannot build unicorn's native code. OTV builds a pure-Python stub wheel at Gradle time from sources in `app/stubs/unicorn/` via `scripts/build_unicorn_stub_wheel.py`, then `install(<wheel path>)` before the FindMy install. Copy this approach; do not check in a prebuilt wheel (a binary blob nobody can review).

**Gradle gotcha (chaquopy#1289).** Flutter declares its Android plugins in `settings.gradle`, so Chaquopy's plugin cannot detect the Android application plugin. Workaround: declare both in a top-level `plugins { }` block. Note plainly: **there is no production open-source Flutter+Chaquopy app to copy.** This combination is the largest unknown in Option B, and it is why Option A exists.

### 6e. Dart models

```dart
class Tracker {
  final String id;    // KeyPair.hashed_adv_key_b64
  final String name;
  factory Tracker.fromJson(Map<String, dynamic> j) =>
      Tracker(id: j['id'] as String, name: j['name'] as String);
}

class LocationReport {
  final double lat, lng, accuracyMeters;
  final DateTime reportedAt;                     // UTC

  /// `reported_at` is UNIX **SECONDS** (int) — lib/trackers.py::serialize_location
  /// does `int(timestamp.timestamp())`.
  ///
  /// DO NOT: DateTime.fromMillisecondsSinceEpoch(j['reported_at'])
  /// 1_758_600_123 read as milliseconds is 1970-01-21, so every report falls
  /// outside the window and the UI shows "no reports" for a tag that is fine.
  /// This is the single most likely bug in the whole client.
  factory LocationReport.fromJson(Map<String, dynamic> j) => LocationReport(
        lat: (j['lat'] as num).toDouble(),
        lng: (j['lng'] as num).toDouble(),
        accuracyMeters: (j['accuracy'] as num).toDouble(),
        reportedAt: DateTime.fromMillisecondsSinceEpoch(
            (j['reported_at'] as num).toInt() * 1000, isUtc: true),
      );
}
```

The locations map is keyed by tracker **name**, not id — inherited from `get_tracker_locations`. The repository re-associates name → id against its own tracker list and drops unknown names with a warning.

`fetch_location_history` has **no `hours` argument** in FindMy.py 0.10.2. The window is filtered client-side, exactly as `lib/trackers.py` does it. Do not send `hours` to Apple expecting it to mean anything.

### 6f. Cache and screens

| Cache rule | Value | Why |
|---|---|---|
| Primary key | `(tracker_id, reported_at_seconds)` | Apple returns overlapping windows; upsert is the dedupe |
| Retention | delete rows older than 7 days after each successful fetch | Apple keeps ~7 days; older rows are unverifiable |
| Render order | cache first, then refresh | The map shows something in a basement |
| Staleness | `now - lastSuccess > 5 min` → amber "last updated HH:MM" | A stale pin that looks live is the worst outcome |

| Screen | Content |
|---|---|
| Tracker list | name + first-grapheme avatar (colour hashed from name, mirroring `web/app.js`), last-seen relative time, accuracy, staleness badge |
| Map | `flutter_map` + OSM tiles (no API key, no vendor SDK), one pin per tag's latest report, accuracy circle from `horizontal_accuracy` |
| History | polyline for one tag; window selector `1h / 6h / 24h / 3d / 7d` → the client-side cutoff |
| Onboarding | Apple ID login → 2FA method pick → code → anisette status, each with its own §9 error state |
| BLE proximity | live RSSI, distance buckets from `tools/scan.py::describe_distance` |

**"No recent reports" — the real `🚗 minicooper` case.** An empty array is not an error and must never render as one:

```
┌──────────────────────────────────────────────┐
│ 🚗 minicooper                                │
│ No reports in the last 24 hours              │
│                                              │
│ A tag only appears when a passing iPhone     │
│ hears it. No reports means one of:           │
│  • nobody with an iPhone has walked past     │
│    (garage, basement, rural area)            │
│  • the battery is dead                       │
│  • it stopped advertising (reset/firmware)   │
│                                              │
│ [ Widen to 7 days ]    [ Scan nearby (BLE) ] │
└──────────────────────────────────────────────┘
```

"Widen to 7 days" re-filters the same fetch before concluding anything. "Scan nearby" is the only way to separate *dead battery* from *out of network range* — which is the entire reason the BLE feature exists.

### 6g. BLE on Android

Mirrors `tools/scan.py`. Parse manufacturer data for company `0x004C`, require first byte `0x12` (`TYPE_OFFLINE_FINDING`) — constants from OTV's `ble/FindMyAdvertisement.java:31,36`. Our own firmware emits exactly that (`firmware/src/ble_stack.c:13-24`: `1e ff 4c 00 12 19 …`).

Identification: a **separated** tag broadcasts 22 key bytes in the payload plus 2 bits in `adv[29]`, and the remaining 6 bytes are the BLE MAC (`set_addr_from_key`). Reassemble the 28-byte advertisement key, SHA-256 it, compare to `Tracker.id`. A tag that still considers itself near its owner truncates the key and **cannot** be identified — show it as "unidentified Find My device", exactly as the CLI does.

`flutter_blue_plus` exposes raw unfiltered advertisement bytes on Android (`ScanRecord.getBytes()`), so this works without platform code. Android is fine.

| Permission | API level | Manifest |
|---|---|---|
| `BLUETOOTH_SCAN` with `android:usesPermissionFlags="neverForLocation"` | 31+ | required; the flag avoids the location-permission prompt because we do not derive location from the scan |
| `BLUETOOTH_CONNECT` | 31+ | required by `flutter_blue_plus` for adapter state, even without GATT |
| `BLUETOOTH`, `BLUETOOTH_ADMIN`, `ACCESS_FINE_LOCATION` | ≤30 | the OS requires location permission for BLE scanning on these versions |
| `FOREGROUND_SERVICE` + `FOREGROUND_SERVICE_LOCATION` / `_CONNECTED_DEVICE` | 34+ | background scanning without a foreground service is throttled to uselessness; OTV uses `foregroundServiceType="location\|connectedDevice"` |

---

## 7. iOS — a separate app, not a port

### 7a. What is impossible, and why (two independent reasons each)

| Blocked thing | Reason 1 | Reason 2 |
|---|---|---|
| App Store distribution | Guideline **2.5.2** — downloading and executing code | Guideline **2.5.1** (private API), no redistribution licence, and AnisetteKit is AGPLv3 with "App Store Distribution Prohibited" |
| `dlopen` of Apple's Android ADI | dyld requires **Mach-O**; the ADI libs are Android **ELF** | Mandatory code signing refuses any downloaded dylib |
| BLE identification of our tags | CoreBluetooth withholds Find My manufacturer data from third-party apps | iOS never exposes the peripheral MAC — and the MAC carries 6 of our 28 key bytes |

The BLE one is fatal in a specific way: **the tag's identity IS the withheld payload.** Evidence: seemoo-lab's AirGuard-iOS identifies AirTags heuristically as "connectable, nameless, no manufacturer data", which is what is left when the payload is filtered out. No Apple primary source confirms this filter — see §14.

### 7b. What iOS could be

A separate **sideloaded** Swift app (AltStore/SideStore), sharing concepts with Android but no code.

| Shareable | Not shareable |
|---|---|
| UI concepts, screen flow, the "no recent reports" copy | Anisette (ELF vs Mach-O) |
| P-224 ECDH → X9.63 KDF → AES-GCM report decryption (pure crypto, CryptoKit) | GSA transport, SRP-6a, the pinned 2006 root CA |
| The tracker/report data model, seconds-vs-ms rule | BLE identification (§7a) |

Anisette would come from **`mahee96/AnisetteKit`**, which runs the same Android ELF under **Unicorn-TCI emulation** (used by SideStore 0.7.0-alpha). Risk assessment, stated plainly: the repo is ~5 weeks old, 5 stars, one maintainer, with contradictory licence metadata, and nobody has independently replicated it. Building a product on it is a bet on one person's unreviewed emulator. Treat iOS as **priority 2, spike-gated**, not as a committed deliverable.

### 7c. The firmware change that would make iOS BLE possible

iOS *does* deliver **service data** (AD type `0x16`) and *does* let an app filter with `scanForPeripherals(withServices:)` — including in the background, which is the only way to scan while the app is not foregrounded. So the tag must advertise a custom 128-bit service UUID in addition to the Apple payload.

Current advert is full (`firmware/src/ble_stack.c:13`): `0x1e` length = 30 bytes payload + 1 length byte = the entire 31-byte legacy PDU. **There is no room.** Adding a 128-bit service UUID AD structure costs 18 bytes. Three concrete options:

| Option | Mechanism | Works on | Cost |
|---|---|---|---|
| **B1 — extended advertising** (recommended) | BLE 5 secondary PDU (up to 255 bytes) carrying both the Apple offline-finding AD and a 128-bit service-data AD | nRF52810 / nRF52832 with SDK 15+ | `adv_params.properties.type = BLE_GAP_ADV_TYPE_EXTENDED_NONCONNECTABLE_NONSCANNABLE_UNDIRECTED`; **not** available on nRF51822 |
| B2 — time-interleave two legacy sets | Alternate the Apple payload and a service-UUID payload, e.g. 1 s each | all chips incl. nRF51822 | Halves the effective Find My advertising rate → fewer network reports. Real cost, not theoretical |
| B3 — scan response | Put the service UUID in the 31-byte scan response | all chips | Requires changing the type from `NONCONNECTABLE_NONSCANNABLE` to **scannable**, which costs power and invites connection attempts. Whether iOS background filtering matches a scan-response-only UUID is **unverified** — §14 |

Concrete spec for B1, against `firmware/src/ble_stack.c`:

```c
/* 128-bit service UUID, generated once for this project (uuidgen), constant
 * across tags: identity stays in the Find My payload, this only makes the tag
 * visible to a CoreBluetooth service filter. */
#define OHW_SERVICE_UUID_128 \
  {0x8f,0x2a,0x1b,0x4c,0x5d,0x6e,0x47,0xf0,0x9a,0x3b,0xc1,0xd2,0xe3,0xf4,0x05,0x16}

static uint8_t ohw_service_adv[] = {
    0x11,                 /* len = 17 */
    0x07,                 /* Complete List of 128-bit Service UUIDs */
    /* UUID, little-endian */
};
/* Emitted as a second AD structure in the extended advertising set, alongside
 * the existing offline_finding_adv[]. */
```

Trade-off to state out loud: a constant UUID across all our tags makes every tag trackable as "an OpenHaystack tag of this project" by anyone scanning — it is a fleet-wide fingerprint. That is the price of iOS visibility. A rotating UUID would defeat the purpose (iOS cannot filter on something it does not know in advance).

---

## 8. Key handling

```
trackers.json (repo, 0600 recommended)
      │  validate_tracker_list()  → private_key is base64 of exactly 28 bytes (P-224 scalar)
      │  wrong length imports fine and then never matches a report → indistinguishable
      │  from a tag out of range, so the tool fails loudly instead
      ▼
tools/export_opentagviewer.py ──► bundle.zip, created 0600 via os.open(..., 0o600)
      │  mode is set AT CREATION, not chmod'ed after — no window where it is 0644
      ▼
transfer to the phone  (the weak link, §11)
      ▼
app import → app-private storage → DELETE the bundle from both machines
```

| Question | Decision | Why |
|---|---|---|
| Transfer mechanism | USB/MTP file copy, or `adb push` | No cloud, no email, no chat. The bundle is equivalent to an SSH private key |
| Deletion | The doc and the tool's output both say delete after import | A forgotten bundle in `~/Downloads` and in the phone's Downloads is two copies of every tag key |
| OpenTagViewer's AES-encrypted (`pyzipper`) bundle | **Support it, do not default to it** | Encryption is real value for a file that crosses a filesystem, but the passphrase then travels beside the file in practice, and a mistyped passphrase produces a failed import the user cannot debug. Offer `--encrypt`, document that the passphrase must travel out-of-band |
| Recommendation | Plain 0600 bundle over USB, deleted immediately; `--encrypt` when the file must touch anything shared | Shortest-lived exposure wins over strongest-cipher-on-a-long-lived-file |

A 28-byte private key cannot be re-derived if lost, and a tag's key cannot be rotated without re-flashing (`flash.sh`, `tools/flash.py`). Losing `trackers.json` means re-flashing every tag.

---

## 9. Failure modes & error taxonomy

Every row is a real, observed condition, not a hypothetical.

| Condition | Detection | User-facing message |
|---|---|---|
| ADI download fails (network, CDN 404, ETag mismatch) | `AdiLibraryFetcher` throws; sha256 mismatch against `adi-libraries.json` | "Could not download Apple's sign-in libraries. Check your connection and retry. If this persists, Apple changed the file — use a remote anisette server in Settings." |
| Manifest drift (Apple shipped a new APK build) | sha256/size mismatch | Same as above, plus a log line naming the expected vs actual size. **Do not call into libraries we cannot vouch for** — symbol names may have moved |
| `dlopen` SIGBUS (OTV #232) | Sacrificial probe process dies; `NativeLoadGuard` record survives the launch | Nothing on screen. Silently fall back to a remote anisette server and note it in Settings |
| Double-load segfault (OTV #135) | Prevented by the load-once lock | n/a — must never reach the user |
| Provisioning `-45061` (`NOT_PROVISIONED`, `AdiError.java:22`) | Return code from `ADIProvisioningStart`/`OTPRequest` | "Sign-in setup is incomplete. Retrying…" → automatic re-provision once, then "Apple refused to set up this device." |
| GSA **503** (client-info blocked) | HTTP 503 from `gsa.apple.com` on a request whose client info names Xcode | "Apple is refusing sign-ins from this app version. An update is needed." — this is §10's daily probe firing in production |
| HTTP **429** (OTV #226) | 429 on provisioning, typically on a reused connection | Close the connection, exponential backoff, retry. Only surface after 3 failures: "Apple is rate-limiting this device. Try again in a few minutes." |
| "Account limit reached" | GSA error text at `com.apple.mobileme` login | "Your Apple ID has too many registered devices. Remove old devices at appleid.apple.com." **Reuse the stored device identity on retry** — `findmy_backend.account_for_login` exists precisely because a fresh identity burns another slot |
| 2FA loop (`au=secondaryAuth`, OTV #236) | GSA keeps returning `secondaryAuth` after a correct code | "Apple keeps asking for a code. Only a refusal spends the code — wait 60 s and retry." Fixed upstream by spending the code only on refusal (OTV PR #237); port that logic |
| HTTP 200 with **empty body** (FindMy.py #185, unresolved upstream) | 200, zero-length body from the reports endpoint | Treat as a transient upstream failure, not as "no reports". "Apple returned an empty response. Retrying…" Never render it as the "no recent reports" screen — that would blame the tag for a server bug |
| Expired session | Reports call rejected after a previously working login | "Your Apple sign-in expired. Sign in again." → onboarding, 2FA required |
| Zero reports, valid 200 with an empty array | Response parsed, array empty | The **"no recent reports"** screen (§6f) — out of range vs dead battery, offer BLE |

Rule: a 200-with-empty-body and a 200-with-empty-array look similar and mean opposite things. Distinguish them at the HTTP layer, not the UI layer.

---

## 10. Upstream drift monitoring

OpenTagViewer runs two jobs because Apple broke this roughly **14 times in 24 months**. Both are worth mirroring even under Option A, because the export bundle is useless if the app cannot sign in.

| Job | Schedule | What it checks | Why that cadence |
|---|---|---|---|
| `check-adi-libraries.yml` | weekly, `cron: 0 5 * * 2` | HEAD/Range `applemusic.apk`, compare `contentLength`/ETag/`lastModified` and per-member sha256 against `adi-libraries.json` | The APK has been byte-stable since 2025-04-15; weekly is enough to catch a change before users do |
| `check-gsa-edge.yml` | daily, `cron: 30 5 * * 1-7` | Real GSA request with our client-info strings, **plus an Xcode-named control probe** | Apple's Sept 2026 block appeared overnight. The control probe is the clever part: if *both* fail it is an outage; if only the Xcode one fails the block is still narrow; if only ours fails, we are the new target |

Our repo runs a reduced version — `.github/workflows/apple-edge.yml`:

1. Weekly APK manifest check (HEAD only, ~0 bytes downloaded, no Apple account needed).
2. Daily GSA edge probe using the pinned FindMy.py, **with the Xcode control**. No credentials: a well-formed unauthenticated request is enough to see a 503-vs-401 difference.
3. Weekly `otv-format-drift.yml` (§5b).
4. On failure: `gh issue create` with label `bug`. Why an issue and not a Slack ping: the failure needs a code change, and an issue is where that lives.

Never run the GSA probe with real credentials on a schedule. A CI job logging into an Apple ID every day is how an Apple ID gets flagged.

---

## 11. Security design

| Threat | Vector | Mitigation | Residual risk |
|---|---|---|---|
| Stolen phone | Device in someone else's hands | OS lock screen + app-private storage; Android app data is not readable without root on a locked device | An **unlocked** stolen phone shows live tag locations and the signed-in Apple account. No app-level lock is specified — see §14 |
| Export bundle in transit | USB copy, but in practice email/Drive/chat | Created 0600 at `os.open` time; documented as SSH-key-equivalent; optional `--encrypt` (§8) | A user who emails the bundle has given away every tag permanently — the key cannot be rotated without re-flashing |
| **Apple ID password in plaintext** | FindMy.py's `AppleAccount.to_json()` embeds `account.password` unencrypted; on the phone that state file sits in app-private storage | App-private storage; never logged; never leaves the device | **Severe and unmitigated by us.** Root, a full device backup, or a forensic image yields full Apple ID credentials. Upstream behaviour; we cannot fix it from here. Say so in the app's own text, do not bury it |
| Tag private key exfiltration | The app's storage, or any copy of the bundle | Keys never sent anywhere (decryption is local); never logged; bundle 0600 | Anyone with root/adb-with-backup on the phone reads them |
| Tile-provider location leak | `flutter_map` requests `z/x/y` tiles from OSM — the provider learns which coordinates you are viewing, which for a tracking app is close to learning where your things are | App-specific `User-Agent`; aggressive tile caching so a revisited area issues no request; a settings field for a self-hosted tile URL; state the leak in the privacy text | With public OSM tiles the provider sees viewed-area coordinates. Only fully fixed by self-hosting tiles |
| Apple-side account risk | Unofficial client; repeated device registrations; rate-limit trips | Reuse the stored device identity on retry; never re-provision casually; no scheduled logins in CI; backoff on 429 | Apple may rate-limit, flag, or lock the Apple ID. There is no appeal process. This is the real cost of the whole approach |
| Malicious/modified ADI libraries | An attacker between the phone and Apple's CDN serving different bytes | sha256 of every member checked against the pinned manifest before it is written to `filesDir`; TLS to `apps.mzstatic.com` | A compromise of Apple's CDN itself would ship signed-looking bytes with a new hash — which the pin turns into a *refusal*, not an execution. Fail closed |
| Downgrade to a remote anisette server | The SIGBUS fallback path sends machine-identity material to a third-party server | The fallback is explicit and visible in Settings, never silent-and-hidden | A user on a #232-affected phone is trusting a stranger's anisette server. Name the server in the UI |

---

## 12. Testing strategy

Existing suite: **74 tests** (2 skipped), `unittest`, fakes not network, in `tests/test_trackers.py`, `tests/test_airtag_crypto.py`, `tests/test_flash.py`, `tests/test_export_opentagviewer.py`. New tests must match that style — no pytest, no new test dependency.

```bash
cd /Users/engineer/workspace/openhaystack-web
.venv/bin/python -m unittest discover -s tests            # must stay green
.venv/bin/python -m unittest tests.test_export_opentagviewer -v
```

### Unit — our repo

| Area | Cases |
|---|---|
| Exporter (exists, extend) | 28-byte key length enforced (27 and 29 both rejected); bundle is 0600 at creation (`stat.S_IMODE`); re-export of an unchanged list is byte-identical (fixed `EXPORTED_AT_MS`); missing exporter path → the install hint, not a traceback; emoji names survive round-trip |
| Format pins (new, `tests/test_otv_format.py`) | Skipped unless `$OPENHAYSTACK_OTV_EXPORTER` is set; asserts `EXPORT_FORMAT_VERSION_WITH_CUSTOM == "0.0.3"`, `CUSTOM_ACCESSORY_TYPE`, `CUSTOM_ACCESSORIES_DIR`, `METADATA_FILENAME` |
| Key derivation (exists) | The owner's real flashed tag: `private_key → adv_key_b64 → hashed_adv_key_b64` must keep reproducing. This is the regression guard for every key path |
| Serialization (exists) | `reported_at` is `int` unix seconds. Never let this become a float or ms |
| BLE parse (new, `tests/test_advertisement.py`) | Reassemble a 28-byte adv key from a synthetic `1e ff 4c 00 12 19 …` payload + MAC; SHA-256 → matches `hashed_adv_key_b64`. Fixture from the real tag values already in `tests/test_trackers.py` |

### Needs a real device (cannot be unit-tested)

| Test | Device | Pass criterion |
|---|---|---|
| ADI Range download | any Android | ≤ 12 MB transferred, all sha256 match |
| `dlopen` of the 11-library closure | ≥ 2 devices, one Android 15+ | all load; no SIGBUS; 16 KB alignment verified |
| Sacrificial probe | a #232-class device if obtainable | app survives, falls back, shows no crash |
| Full login incl. SMS 2FA | real Apple ID | reports returned. **No dated successful SMS 2FA login exists after 2026-09-14** — §14 |
| BLE identification | Android + a real powered tag | our tag matched by name, same result as `tools/scan.py` |
| iOS BLE | real iPhone + tag | expected to **fail** on current firmware; the point is to document it, not to hope |

### Flutter (Option B only)

```bash
cd mobile && flutter test                     # unit + widget + golden
flutter test integration_test/                # against a fake bridge
```

| Kind | Cases |
|---|---|
| Unit | `LocationReport.fromJson`: `1758600123` → 2025-09-23 UTC, **not** 1970 (the headline bug); every §9 condition maps to the right typed error |
| Widget | empty array renders the "no recent reports" card with both causes **and** the BLE action; empty *body* renders a retry, not that card |
| Golden | tracker list, "no recent reports", error banner |

### Manual verification checklist

```bash
# 1. export
.venv/bin/python -m unittest discover -s tests            # 74 green
OPENHAYSTACK_OTV_EXPORTER=/tmp/otv/python \
  .venv/bin/python tools/export_opentagviewer.py trackers.json -o /tmp/tags.zip
ls -l /tmp/tags.zip                                       # -rw-------
python -m zipfile -l /tmp/tags.zip                        # OPENTAGVIEWER.yml + CustomAccessories/
unzip -p /tmp/tags.zip OPENTAGVIEWER.yml                  # version: 0.0.3

# 2. phone (Option A)
adb push /tmp/tags.zip /sdcard/Download/
#   import in OpenTagViewer → sign in → verify both tags appear
adb logcat -s AdiLibraryFetcher:* NativeAdi:* LocalAnisette:*   # watch the pipeline

# 3. BLE cross-check
.venv/bin/python tools/scan.py --seconds 30               # desktop truth
#   compare with the phone's scan result for the same tag

# 4. cleanup
shred -u /tmp/tags.zip 2>/dev/null || rm -f /tmp/tags.zip
adb shell rm /sdcard/Download/tags.zip
```

---

## 13. Migration & rollout

Each step leaves the repo working and the suite green.

| Phase | Step | Green check |
|---|---|---|
| **0 — done** | `tools/export_opentagviewer.py` + tests (commit `dc82451`) | 74 tests pass |
| 1 | Add `tests/test_otv_format.py` (skipped without the exporter path) and `.github/workflows/otv-format-drift.yml` | suite green; workflow runs on dispatch |
| 2 | Add `.github/workflows/apple-edge.yml` (weekly APK, daily GSA + Xcode control) | first run reports the current state |
| 3 | Document the Option A end-to-end flow in `README.md`: export → transfer → import → delete | manual checklist §12 passes on a real phone |
| 4 | **Disk gate** (§14) — free ≥ 20 GB before any Android build work | `df -h /System/Volumes/Data` |
| 5 | Add `tests/test_advertisement.py` (BLE payload → key → hash), pure Python, no device | suite green |
| 6 | **Decision point.** If Option A is adequate, stop here. Everything above is maintenance, not development | — |
| 7 | Option B spike: bare Flutter + Chaquopy app that imports FindMy.py and prints its version on a device. This is the #1289 risk, isolated | APK runs on a device |
| 8 | Option B spike: port the anisette Java + `adi.cpp` (MIT, attribution retained), reach `ADIOTPRequest` returning bytes | OTP headers produced on 2 devices |
| 9 | Option B: login + 2FA + fetch + map | integration tests pass |
| 10 | Option B: BLE screen, foreground service, permissions | matches `tools/scan.py` on the same tag |
| 11 | iOS spike (priority 2): AnisetteKit under Unicorn-TCI, sideloaded, one successful report fetch | go/no-go on iOS at all |
| 12 | Firmware service-UUID change (§7c) only if step 11 says go | tags still report to Find My **and** appear to a CoreBluetooth service filter |

Steps 7 and 8 are where Option B either becomes real or gets cancelled. Do not build screens before they pass.

---

## 14. Open questions

Honest gaps. None of these are hand-waved.

1. **No Apple primary source confirms the CoreBluetooth Find My filter.** The claim that iOS withholds `0x004C` Find My manufacturer data from third-party apps is *inferred* from seemoo-lab/AirGuard-iOS's heuristic ("connectable, nameless, no manufacturer data") — a strong signal, not documentation. It should be measured directly on a real iPhone before the firmware change in §7c is committed.
2. **AnisetteKit is unreplicated.** `mahee96/AnisetteKit`: ~5 weeks old, 5 stars, one maintainer, contradictory licence metadata. Nobody outside SideStore has reproduced it. Betting the iOS product on it is betting on one unreviewed emulator.
3. **No dated successful SMS 2FA login after 2026-09-14.** Everything after that date is inference from code, not from an observed sign-in. Whether the current client-info strings still complete a full 2FA login today is **unverified**.
4. **Is `com.apple.gs.xcode.auth` next?** FindMy.py 0.10.2 still sends `X-Apple-App-Info: com.apple.gs.xcode.auth` and `X-Xcode-Version` (`anisette.py:175-176`) after Apple blocked `com.apple.dt.Xcode`. Nobody knows whether that is an oversight Apple will close or a header it ignores.
5. **Does omnisette compile for Android/iOS targets?** Unverified. `SideStore/apple-private-apis` has been dormant since 2024-11-14, its `android_loader` targets desktop and has no Android CI. A `grep` of `icloud-auth/src/client.rs` for `fmip|findmy|gateway.icloud|searchparty|mobileme|delegate` returns **zero hits** — it has complete GSA/SRP-6a + SMS 2FA but **no report fetch, no delegate call, no P-224 decrypt**. The Rust path is a mirage today; do not plan around it.
6. **Disk-space gate.** Measured on this host: `/System/Volumes/Data` 228 GiB, **4.4 GiB free, 98% full**. (The brief said ~2.4 GiB; the measurement is above, taken 2026-09-22.) JDK 17, Android SDK+NDK, adb and Rust are installed. An Android/NDK build needs several GB of intermediates. **This blocks steps 7+ and must be cleared first.**
7. **Flutter + Chaquopy has no production precedent.** No open-source app combines them in production. The #1289 workaround is documented but unproven at our scale. Step 7 exists to find out cheaply.
8. **Does iOS background `scanForPeripherals(withServices:)` match a UUID that appears only in the scan response** (firmware option B3)? Unverified. If it does not, B3 is dead and only extended advertising (B1) works.
9. **Chaquopy's `cryptography` cap at 42.0.8** — does the pinned FindMy.py fork work within it? Must be checked at step 7, not assumed.
10. **App-level lock on the phone.** Not specified. Worth it given the OS already gates the device? It adds friction on every launch and protects only the unlocked-and-handed-over case.
11. **Constant service UUID = fleet fingerprint.** §7c makes every one of our tags identifiable as "an OpenHaystack tag of this project" to any scanner. Acceptable price for iOS visibility, or not? Product call.

---

## 15. Known weaknesses

| Weakness | Effect | Why it is accepted |
|---|---|---|
| Apple can break the pipeline overnight | The whole product stops. ~14 breakages in 24 months; the Sept 2026 Xcode block is the most recent | Inherent to an unofficial client. §10 turns "discovered by users" into "detected by CI", which is the only available improvement |
| Apple ID password stored in plaintext on the phone | Root or a full backup yields full credentials | Upstream `AppleAccount.to_json()` behaviour. Not fixable from here |
| Apple ID may be rate-limited or flagged | No appeal process | Cost of the approach; mitigated only by not re-provisioning casually |
| iOS is a second product, probably late, possibly never | Android-only for the foreseeable future | Two independent blockers (ELF vs Mach-O, code signing) plus an unreplicated dependency |
| iOS cannot see our tags over BLE without a firmware change | The "dead battery or out of range?" answer is Android-only | Platform restriction; §7c is the only way out and it costs a re-flash of every tag |
| Option B duplicates work that already exists and works | Weeks of effort for UI control | Which is why Option A ships first and step 6 is an explicit stop |
| The key bundle is a file a human moves by hand | One careless email loses every tag permanently | No server means no key-distribution channel. Keys cannot be rotated without re-flashing |
| Build host is at 98% disk | No Android build can start | Operational, fixable, but a hard gate today |
