from __future__ import annotations

from pathlib import Path
import math
import struct
import wave

ROOT = Path(__file__).resolve().parents[1]

CHANNEL_ID = "aplus_updates_signature_v1"
SOUND_RESOURCE = "solution_signature"
SOUND_FILE = f"{SOUND_RESOURCE}.wav"
ICON_RESOURCE = "ic_stat_aplus"


def replace_once(path: Path, old: str, new: str, marker: str | None = None) -> None:
    text = path.read_text(encoding="utf-8")
    if marker and marker in text:
        return
    if old not in text:
        raise RuntimeError(f"Patch anchor not found in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_backend() -> None:
    path = ROOT / "backend/core/push_notifications.py"
    replace_once(
        path,
        "DEFAULT_BUNDLE_ID = 'de.aplussolution.workforce'\n",
        "DEFAULT_BUNDLE_ID = 'de.aplussolution.workforce'\n"
        f"ANDROID_NOTIFICATION_CHANNEL_ID = '{CHANNEL_ID}'\n"
        f"ANDROID_NOTIFICATION_SOUND = '{SOUND_RESOURCE}'\n"
        f"ANDROID_NOTIFICATION_ICON = '{ICON_RESOURCE}'\n",
        marker=f"ANDROID_NOTIFICATION_CHANNEL_ID = '{CHANNEL_ID}'",
    )
    replace_once(
        path,
        "                    'sound': 'default',\n                    'channel_id': 'aplus_updates',\n",
        "                    'sound': ANDROID_NOTIFICATION_SOUND,\n"
        "                    'channel_id': ANDROID_NOTIFICATION_CHANNEL_ID,\n"
        "                    'icon': ANDROID_NOTIFICATION_ICON,\n",
        marker="'channel_id': ANDROID_NOTIFICATION_CHANNEL_ID",
    )

    text = path.read_text(encoding="utf-8")
    ios = text.split("def _send_ios(", 1)[1]
    if "'sound': 'default'" not in ios:
        raise RuntimeError("iOS APNs sound changed unexpectedly; refusing to continue.")


def patch_frontend_registration() -> None:
    path = ROOT / "frontend/src/NativePushRegistration.tsx"
    replace_once(
        path,
        "const APP_ID = 'de.aplussolution.workforce';\n",
        "const APP_ID = 'de.aplussolution.workforce';\n"
        f"const ANDROID_PUSH_CHANNEL_ID = '{CHANNEL_ID}';\n"
        f"const ANDROID_PUSH_SOUND = '{SOUND_FILE}';\n"
        f"const ANDROID_PUSH_ICON = '{ICON_RESOURCE}';\n",
        marker=f"const ANDROID_PUSH_CHANNEL_ID = '{CHANNEL_ID}';",
    )
    replace_once(
        path,
        "        channelId: Capacitor.getPlatform() === 'android' ? 'aplus_updates' : undefined,\n"
        "        extra: notification.data || {},",
        "        channelId: Capacitor.getPlatform() === 'android' ? ANDROID_PUSH_CHANNEL_ID : undefined,\n"
        "        sound: Capacitor.getPlatform() === 'android' ? ANDROID_PUSH_SOUND : undefined,\n"
        "        smallIcon: Capacitor.getPlatform() === 'android' ? ANDROID_PUSH_ICON : undefined,\n"
        "        extra: notification.data || {},",
        marker="smallIcon: Capacitor.getPlatform() === 'android' ? ANDROID_PUSH_ICON : undefined",
    )
    replace_once(
        path,
        "          await PushNotifications.createChannel({\n"
        "            id: 'aplus_updates',\n"
        "            name: 'A+ Solution Updates',\n"
        "            description: 'Schichten, Verträge, Nachrichten und wichtige Änderungen',\n"
        "            importance: 5,\n"
        "            visibility: 1,\n"
        "            sound: 'default',\n"
        "            vibration: true,\n"
        "          });",
        "          await PushNotifications.createChannel({\n"
        "            id: ANDROID_PUSH_CHANNEL_ID,\n"
        "            name: 'A+ Solution Updates',\n"
        "            description: 'Schichten, Verträge, Nachrichten und wichtige Änderungen',\n"
        "            importance: 5,\n"
        "            visibility: 1,\n"
        "            sound: ANDROID_PUSH_SOUND,\n"
        "            vibration: true,\n"
        "          });",
        marker="id: ANDROID_PUSH_CHANNEL_ID,",
    )
    replace_once(
        path,
        "            await LocalNotifications.createChannel({\n"
        "              id: 'aplus_updates',\n"
        "              name: 'A+ Solution Updates',\n"
        "              description: 'Schichten, Verträge, Nachrichten und wichtige Änderungen',\n"
        "              importance: 5,\n"
        "              visibility: 1,\n"
        "              sound: 'default',\n"
        "              vibration: true,\n"
        "            });",
        "            await LocalNotifications.createChannel({\n"
        "              id: ANDROID_PUSH_CHANNEL_ID,\n"
        "              name: 'A+ Solution Updates',\n"
        "              description: 'Schichten, Verträge, Nachrichten und wichtige Änderungen',\n"
        "              importance: 5,\n"
        "              visibility: 1,\n"
        "              sound: ANDROID_PUSH_SOUND,\n"
        "              vibration: true,\n"
        "            });",
        marker="await LocalNotifications.createChannel({\n              id: ANDROID_PUSH_CHANNEL_ID,",
    )


def write_sound(path: Path) -> None:
    sample_rate = 44100

    def note(freq: float, duration: float, amp: float, attack: float, release: float, decay: float) -> list[float]:
        count = int(sample_rate * duration)
        attack_n = max(1, int(sample_rate * attack))
        release_n = max(1, int(sample_rate * release))
        values: list[float] = []
        for i in range(count):
            t = i / sample_rate
            env = math.exp(-decay * t)
            if i < attack_n:
                env *= i / attack_n
            if i >= count - release_n:
                env *= max(0.0, (count - 1 - i) / release_n)
            values.append(amp * math.sin(2 * math.pi * freq * t) * env)
        return values

    def gap(duration: float) -> list[float]:
        return [0.0] * int(sample_rate * duration)

    # Exact selected Signature Motif: three soft ascending notes, ~0.616 s total.
    samples = (
        note(440, 0.17, 0.48, 0.012, 0.09, 2.0)
        + gap(0.018)
        + note(550, 0.17, 0.44, 0.012, 0.09, 2.0)
        + gap(0.018)
        + note(660, 0.24, 0.40, 0.014, 0.14, 1.8)
    )
    peak = max(abs(value) for value in samples) or 1.0
    samples = [max(-1.0, min(1.0, value / peak * 0.58)) for value in samples]

    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(struct.pack("<h", int(value * 32767)) for value in samples))


def write_icon(path: Path) -> None:
    # Android small notification icons are monochrome masks. The supplied
    # notif-icon.svg contains the white plus mark; center that mark as an Android vector.
    svg = ROOT / "notif-icon.svg"
    if not svg.exists() or ">+</" not in svg.read_text(encoding="utf-8"):
        raise RuntimeError("notif-icon.svg is missing or does not contain the supplied + mark.")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<vector xmlns:android=\"http://schemas.android.com/apk/res/android\"
    android:width=\"24dp\"
    android:height=\"24dp\"
    android:viewportWidth=\"24\"
    android:viewportHeight=\"24\">
    <path
        android:fillColor=\"#FFFFFFFF\"
        android:pathData=\"M10,3.5h4v6.5h6.5v4H14v6.5h-4V14H3.5v-4H10z\" />
</vector>
""",
        encoding="utf-8",
    )


def patch_prepare_native() -> None:
    path = ROOT / "frontend/scripts/prepare-native.mjs"
    text = path.read_text(encoding="utf-8")

    if "function installAndroidNotificationBranding(manifestPath)" not in text:
        anchor = "function patchAndroid() {"
        if anchor not in text:
            raise RuntimeError("prepare-native Android patch anchor missing")
        function = r'''function installAndroidNotificationBranding(manifestPath) {
  const assetsDir = path.join(cwd, 'native-assets', 'android');
  const soundSource = path.join(assetsDir, 'solution_signature.wav');
  const iconSource = path.join(assetsDir, 'ic_stat_aplus.xml');
  if (!fs.existsSync(soundSource)) throw new Error(`Android notification sound source not found: ${soundSource}`);
  if (!fs.existsSync(iconSource)) throw new Error(`Android notification icon source not found: ${iconSource}`);

  const resDir = path.join(cwd, 'android', 'app', 'src', 'main', 'res');
  const rawDir = path.join(resDir, 'raw');
  const drawableDir = path.join(resDir, 'drawable');
  fs.mkdirSync(rawDir, { recursive: true });
  fs.mkdirSync(drawableDir, { recursive: true });
  fs.copyFileSync(soundSource, path.join(rawDir, 'solution_signature.wav'));
  fs.copyFileSync(iconSource, path.join(drawableDir, 'ic_stat_aplus.xml'));

  let xml = fs.readFileSync(manifestPath, 'utf8');
  const iconMeta = '        <meta-data android:name="com.google.firebase.messaging.default_notification_icon" android:resource="@drawable/ic_stat_aplus" />';
  const channelMeta = '        <meta-data android:name="com.google.firebase.messaging.default_notification_channel_id" android:value="aplus_updates_signature_v1" />';
  if (!xml.includes('com.google.firebase.messaging.default_notification_icon')) {
    xml = xml.replace(/<application\b[^>]*>/, (match) => `${match}\n${iconMeta}`);
  }
  if (!xml.includes('com.google.firebase.messaging.default_notification_channel_id')) {
    xml = xml.replace(/<application\b[^>]*>/, (match) => `${match}\n${channelMeta}`);
  }
  fs.writeFileSync(manifestPath, xml);
  console.log('Installed Android A+ notification icon and Signature Motif sound.');
}

'''
        text = text.replace(anchor, function + anchor, 1)

    if "  installAndroidNotificationBranding(manifestPath);" not in text:
        old = "  installAndroidLauncherArtwork(manifestPath);\n  console.log('Prepared Android API 36, foreground location and native push permissions.');"
        new = "  installAndroidLauncherArtwork(manifestPath);\n  installAndroidNotificationBranding(manifestPath);\n  console.log('Prepared Android API 36, foreground location, native push permissions and notification branding.');"
        if old not in text:
            raise RuntimeError("prepare-native branding call anchor missing")
        text = text.replace(old, new, 1)

    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_backend()
    patch_frontend_registration()

    assets = ROOT / "frontend/native-assets/android"
    write_sound(assets / SOUND_FILE)
    write_icon(assets / f"{ICON_RESOURCE}.xml")
    patch_prepare_native()

    print("Android notification branding source patch applied.")
    print(f"channel={CHANNEL_ID} sound={SOUND_FILE} icon={ICON_RESOURCE}")
    print("iOS APNs sound remains default.")


if __name__ == "__main__":
    main()
