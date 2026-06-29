# HDA Mic Diagnosis on x1tablet (X1 Tablet Gen 3, ALC295 17aa:2263)

## The bug, in one sentence

Lenovo X1 Tablet Gen 3 (subsystem `17aa:2263`) has **no entry in the kernel's ALC295 fixup table** (`patch_realtek.c`). The codec runs on pure autoconfig, which misroutes input → internal mic records bias voltage + thermal noise → white noise.

## Hardware fingerprint (how to confirm you're on this machine)

```bash
# 1. Codec identification
cat /sys/class/sound/hwC0D0/{vendor_id,chip_name,subsystem,subsystem_id}
# Expected: 0x10ec0295 / ALC295 / 0x17aa2263 / 17aa:2263

# 2. Kernel autoconfig log (look for "ALC295:" line, no "picked fixup")
sudo dmesg | grep -E 'alc295|hdaudio'
# Expected:
#   snd_hda_codec_realtek hdaudioC0D0: autoconfig for ALC295: line_outs=2 ...
#   snd_hda_codec_realtek hdaudioC0D0:    inputs:
#   snd_hda_codec_realtek hdaudioC0D0:      Internal Mic=0x12
#   snd_hda_codec_realtek hdaudioC0D0:      Mic=0x19
# Notably NO "picked fixup for PCI SSID 17aa:2263" line — the kernel has no
# quirk for this subsystem.

# 3. Confirm no fixup entry exists (compare against known-working siblings)
curl -sL https://raw.githubusercontent.com/torvalds/linux/v6.12/sound/pci/hda/patch_realtek.c -o /tmp/pr.c
grep -c '0x17aa, 0x2263' /tmp/pr.c
# Expected: 0  (this subsystem is not in the fixup table)
```

## Why the noise happens

HDA pin config (from `/sys/class/sound/hwC0D0/init_pin_configs`):

```
0x12 0x90a60130   ← Internal Mic (fixed function, mono)  ← the only real input
0x18 0x411111f0   ← No Connection (not used)
0x19 0x04a11040   ← Physically a headphone jack, but autoconfig promotes it to "Mic"
0x21 0x04211020   ← Headphone jack (external)
```

Kernel autoconfig sees pin 0x19 has "jack" connectivity and re-interprets it as a Mic input. But physically pin 0x19 is the headset jack, and pin 0x12 (the real internal mic) has its `Mic Boost` control exposed but the pin path may be misrouted by the missing fixup.

The classic symptom (verified):
- RMS = -22 dBFS (loud!)
- DC offset = -500 to +500 (huge — bias voltage)
- Spectrum: massive DC + sub-200 Hz, then flat noise floor 200-8000 Hz
- No real signal in 300-3400 Hz voice band
- Boosting "Internal Mic Boost" amplifies noise but DC polarity flips — classic unloaded-pin signature

Use the spectrum probe script to confirm:
```bash
arecord -D plughw:0,0 -f S16_LE -r 48000 -d 3 /tmp/probe.wav
python3 /home/dr/.hermes/skills/local_share/sway/pipewire-audio-routing/scripts/mic-spectrum-probe.py /tmp/probe.wav
# Exits 1 with "OPEN/UNLOADED PIN" warning if this is the bug.
```

## Fix path A — try SOF driver (preferred, less invasive)

The PCI device has `snd_sof_pci_intel_skl` available. Force SOF instead of legacy `snd_hda_intel`:

```bash
echo "options snd-intel-dspcfg dsp_driver=3" | sudo tee /etc/modprobe.d/sof-fix.conf
sudo update-initramfs -u
sudo reboot
```

After reboot verify:
```bash
lspci -k -s 00:1f.3 | grep 'driver in use'
# Should show: snd_sof_pci_intel_skl (or similar SOF driver) instead of snd_hda_intel
```

If the X1 Tablet Gen 3 has a SOF topology in `/usr/lib/firmware/intel/sof-tplg/` (it does on a current Debian 13 install), SOF will initialize the codec with the right pin routing.

## Fix path B — hdajackretask manual pin remap (fallback)

If SOF doesn't work or isn't desired:

```bash
sudo apt install alsa-tools-gui
hdajackretask
```

In the GUI:
1. Check "Show unconnected pins"
2. Find pin `0x19` → set to "Not connected"
3. Find pin `0x12` → confirm it stays as "Internal Microphone"
4. Click "Install boot override" (writes `/etc/modprobe.d/hda-jack-retask.conf`)
5. Reboot

## Fix path C — external USB mic

If the user is running headless / docked and doesn't care about the built-in mic, a USB mic sidesteps the whole HDA mess.

## Known-similar models (worked examples in kernel source)

For reference, these Lenovo subsystem IDs DO have ALC295 fixups (their quirks show what kind of pin remap works for Thinkpads in this era):

| Subsystem | Model | Fixup |
|---|---|---|
| 0x17aa, 0x2215 | Thinkpad | ALC269_FIXUP_LIMIT_INT_MIC_BOOST |
| 0x17aa, 0x225d | Thinkpad T480 | ALC269_FIXUP_LIMIT_INT_MIC_BOOST |
| 0x17aa, 0x2292 | X1 Carbon 7th | ALC285_FIXUP_THINKPAD_HEADSET_… |
| 0x17aa, 0x22be | X1 Carbon 8th | ALC285_FIXUP_THINKPAD_HEADSET_… |

`ALC269_FIXUP_LIMIT_INT_MIC_BOOST` is the most likely candidate to also fix 0x2263 — caps the mic boost to prevent saturation on Thinkpads. Test with:

```bash
echo "options snd-hda-intel model=alc269-fixup-limit-int-mic-boost" | sudo tee /etc/modprobe.d/alc295-thinkpad.conf
# Then check the model= list for an exact match, or blacklist and reboot
```

But the SOF path is preferred because it doesn't require fighting the legacy driver.

## Reference: HDA pin config word decode

Each line in `init_pin_configs` is `0xNNAABBCD` where:

```
Bit 31-30 (NN): Port Connectivity
                00 = Jack (1/8", 1/4", etc.)
                01 = No Connection
                10 = Fixed Function (built-in device)
                11 = Both jack and fixed function

Bit 29-28 (AA): Location
                00 = N/A
                01 = Internal
                10 = Separate chassis
                11 = Lifted (panel) / Mobile lid

Bit 27-24 (BB): Default Device
                0  = Line out
                1  = Speaker
                2  = HP out
                3  = CD / Mic
                4  = SPDIF out
                5  = Digital other out
                6  = Modem line / Side
                7  = Modem handset
                8  = Line in
                9  = Aux
                A  = Mic in
                B  = Telephone
                C  = SPDIF in
                D  = Digital other in
                E  = Reserved
                F  = Other

Bit 23-20 (CC): Connection Type
                0  = Unknown
                1  = 1/8" stereo/mono
                2  = 1/4" stereo/mono
                3  = ATAPI internal
                4  = RCA
                5  = Optical
                6  = Other digital
                7  = Other analog
                8  = Multichannel analog (DIN)
                9  = XLR/Professional
                A  = RJ-11 (modem)
                B  = Combination
                E  = Mini-DIN
                F  = Other

Bit 19-16 (DD): Color
                0  = Unknown
                1  = Black
                2  = Grey
                3  = Blue
                4  = Green
                5  = Red
                6  = Orange
                7  = Yellow
                8  = Purple
                9  = Pink
                A  = Reserved
                ...
                F  = White
```

## Reference: the `wpctl` ID shift gotcha

`wpctl` reassigns node IDs on each session/restart, and sometimes after `set-default`. **Always re-run `wpctl status` immediately before `wpctl inspect <id>`** — don't trust the ID you saw 30 seconds ago. This is critical for debugging because `inspect` against a stale ID will show a completely unrelated device (e.g., a V4L2 camera instead of the audio source you wanted).
