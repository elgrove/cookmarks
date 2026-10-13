---
name: deploy-pixel
description: Install a new Cookmarks version on the Pixel phone over ADB. Use when the user asks to deploy to the Pixel, install the app on the Pixel, or put a new version on the phone.
allowed-tools: Bash Read Glob
---

# Deploy Cookmarks to the Pixel

The Pixel runs the **release** build. Build from trunk `main`, publish to apkbin (via the
`ship-apk` skill flow), then install over ADB. Never uninstall the on-device app without
asking first — that wipes its local session and caches.

## 0. Find the Pixel

```sh
/opt/android-sdk/platform-tools/adb devices -l
```

Use the device whose model is `Pixel_10_Pro` (wireless TLS serial). If it is absent, stop
and say so — do not touch the emulator or any other device. Pass its serial to every
`adb` call with `-s <serial>` (shown as `$S` below).

## 1. Build and verify the release

```sh
cd /home/aaron/dev/cookmarks/android
./gradlew :app:assembleRelease
BT=$(ls -d /opt/android-sdk/build-tools/* | sort -V | tail -1)
$BT/apksigner verify --print-certs app/build/outputs/apk/release/app-release.apk
```

Proceed only if `Signer #1 certificate DN: CN=Cookmarks` with SHA-256 digest
`5efae98fcf58d9ff3b7c2c17aa62e677257960b171aca7f4e4f07d61e4c052aa`.
That digest matches every shipped release — a different digest means the wrong key.

## 2. Publish to apkbin

Copy the verified APK to `/home/aaron/docker/apkbin/apk/` as `cookmarks-YYYY-MM-DD.apk`
(`-vN` suffix when the date is taken). Install link: `http://10.0.0.11:8111/apk/<file>`.

## 3. Install

```sh
/opt/android-sdk/platform-tools/adb -s $S install -r /home/aaron/docker/apkbin/apk/<file>
```

Confirm with `adb -s $S shell dumpsys package com.cookmarks.app` (fresh `lastUpdateTime`).

## Signature mismatch

`INSTALL_FAILED_UPDATE_INCOMPATIBLE` means the on-device copy was signed with a
different key (e.g. a debug build from another machine — seen October 2026). Diagnose
before acting:

```sh
P=$(adb -s $S shell pm path com.cookmarks.app | tr -d '\r' | sed 's/package://')
adb -s $S pull "$P" /tmp/ondevice.apk
$BT/apksigner verify --print-certs /tmp/ondevice.apk   # compare digest with §1
keytool -list -v -keystore ~/.android/debug.keystore -storepass android | grep SHA256
```

If the on-device digest matches neither the release cert nor the local debug keystore,
no build from this machine can update it. The only fix is `adb uninstall` plus fresh
install — ask the user first. Server data is safe; only the local session and caches go.

Debug builds (`assembleDebug` + `install -r`) are for dev iteration only. The debug key
lives in the per-machine `~/.android/debug.keystore`, so a debug APK from another
machine will not update either.

## Limits

Do not run performance or network measurements on the Pixel unless the user explicitly
asks. Installing is not testing.
