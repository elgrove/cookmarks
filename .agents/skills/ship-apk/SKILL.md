---
name: ship-apk
description: Build, verify, and publish a signed Cookmarks Android release APK to apkbin. Use when the user asks to ship, release, build, or publish the Cookmarks APK, or get a new Cookmarks build onto the Pixel.
allowed-tools: Bash Read Glob
---

# Ship the Cookmarks APK

Build and publish a **signed** Android release APK from Cookmarks to apkbin. Never publish an
unsigned APK: it cannot update the existing Cookmarks installation on the phone.

## Build and verify

The persistent Cookmarks release keystore is configured locally in the gitignored
`android/local.properties`; it must name `/home/aaron/.android/cookmarks-release.keystore` and
the `cookmarks` alias. Do not add signing credentials to tracked project files. Build without a
`-PcookmarksBaseUrl` override so the phone uses the default Tailscale production API:

```sh
cd /home/aaron/dev/cookmarks/android
./gradlew :app:assembleRelease
```

The required output is `app/build/outputs/apk/release/app-release.apk`. Before publishing,
verify it using the latest installed Android build tools:

```sh
BT=$(ls -d /opt/android-sdk/build-tools/* | sort -V | tail -1)
$BT/apksigner verify --verbose --print-certs app/build/outputs/apk/release/app-release.apk
```

Proceed only if verification succeeds and reports `Signer #1 certificate DN: CN=Cookmarks`.
If the release APK is absent, unsigned, or has a different signer, stop rather than publishing.

## Publish

Use the `publish-to-apkbin` skill with the verified `app-release.apk` and app name `cookmarks`.
It copies the APK to `/home/aaron/docker/apkbin/apk/` as `cookmarks-YYYY-MM-DD.apk`, adding a
`-vN` suffix when that date is already in use. Report the final file path, size, and this link:

`http://10.0.0.11:8111/apk/<filename>`
