# Cookmarks Android

Native Kotlin + Jetpack Compose companion app: browse books, recipes and lists, favourite
and organise recipes, and swipe-read a book's recipes with progress synced to the desktop
SPA. Talks to the same API as the SPA, hardcoded to the Tailscale address
`http://100.76.187.39:8789` (override per build with `-PcookmarksBaseUrl=...`).

## Requirements

- JDK 17
- Android SDK at the path in `local.properties` (`sdk.dir=/opt/android-sdk` on `main`),
  with platform + build-tools 36.

## Build

```bash
cd android
./gradlew :app:assembleDebug          # debug APK
./gradlew :app:testDebugUnitTest      # JVM tests (contract pins + logic)
./gradlew :app:assembleRelease        # signed release APK (needs keystore config below)
```

APKs land in `app/build/outputs/apk/{debug,release}/`.

## Release signing

The release build signs with a locally generated keystore, configured in
`local.properties` (gitignored) or the matching environment variables:

```properties
cookmarks.keystore=/home/aaron/.android/cookmarks-release.keystore
cookmarks.keystore.password=...
cookmarks.key.alias=cookmarks
cookmarks.key.password=...
```

Env fallbacks: `COOKMARKS_KEYSTORE`, `COOKMARKS_KEYSTORE_PASSWORD`, `COOKMARKS_KEY_ALIAS`,
`COOKMARKS_KEY_PASSWORD`. Generate the keystore once with:

```bash
keytool -genkeypair -keystore ~/.android/cookmarks-release.keystore -alias cookmarks \
  -keyalg RSA -keysize 2048 -validity 10000
```

With no keystore configured, `assembleRelease` produces an unsigned APK. Keep the same
keystore forever — the phone refuses to update an app whose signature changed.

## Publish to the phone

```bash
./gradlew :app:assembleRelease
```

Then publish `app/build/outputs/apk/release/app-release.apk` with the `publish-to-apkbin`
skill and install it on the Pixel from the download server.

## Emulator verification

The pattern that works on `main` (AVD `cookmarks`, Android 36 image):

```bash
sqlite3 ~/docker/cookmarks/data/db.sqlite3 ".backup '/tmp/cm.sqlite3'"   # prod DB copy
COOKMARKS_DB_PATH=/tmp/cm.sqlite3 uv run uvicorn app.main:app --port 9788  # from backend/
./gradlew :app:assembleDebug -PcookmarksBaseUrl=http://10.0.2.2:9788
emulator -avd cookmarks -no-window &
adb install app/build/outputs/apk/debug/app-debug.apk
adb exec-out screencap -p > screen.png
```

Cleartext HTTP is scoped by `res/xml/network_security_config.xml` to the Tailscale address
and the emulator host alias (`10.0.2.2`); a different `cookmarksBaseUrl` host needs adding
there too.
