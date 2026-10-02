# vgm2syx

Extract **YM2151 (OPM)** FM voices from VGM/VGZ files and convert them into
**Yamaha TX81Z SysEx banks**. Multiple songs can be combined into one collection,
with a table showing where each voice is used.

The conversion follows the MDX voice importer in
the local development version of
[masanaohayashi/TX81Z](https://github.com/masanaohayashi/TX81Z)
(`Source/Import/MdxVoice.h`; this importer was not present in the public repository
at the time of publication).
It preserves the operator ordering and uses the firmware's frequency lookup,
output-level curve, and algorithm-dependent carrier compensation.

## Quick start

Python 3.9 or later. The standalone script needs no third-party libraries.

```sh
python3 vgm2syx.py song.vgm -o result
python3 vgm2syx.py /path/to/game-vgms -o result --prefix GM
python3 vgm2syx.py song1.vgm song2.vgz -o result
```

Alternatively, install the command from this checkout:

```sh
python3 -m pip install .
vgm2syx /path/to/game-vgms -o result --prefix GM
```

Input folders are searched recursively. Choose a new or empty output folder;
existing results are not overwritten. Input files are never modified.

## Output

| File | Contents |
| --- | --- |
| `bank_001.syx`, … | 32-voice TX81Z bulk dumps, 4,104 bytes each |
| `source_001.mdx`, … | Original YM2151 voices for MDX preview; empty music tracks |
| `usage.tsv` | Voice, bank/slot, song, chip/channel, key-on count, first/last use, estimated pitch range |
| `voices.json` | Source register snapshots, usage, and conversion warnings |
| `README.txt` | Japanese explanation of the generated files |

Load a bank into the TX81Z software. Banks are split every 32 voices; unused
slots contain silent placeholders named `INIT VOICE`. MDX files are split every
256 voices, with local voice IDs starting at zero in each file.

Voices are ordered by key-on count. Common carrier-volume changes are grouped,
and the most frequent original snapshot is selected as the representative.
Pass `--keep-volume-variants` to retain those variations separately.

Options:

- `--prefix GM`: ASCII alphanumeric voice-name prefix, up to five characters.
- `--midi-channel 1`: SysEx channel, 1–16; default 1.
- `--keep-volume-variants`: keep common carrier-volume variations separate.
- `--version`: print the version.

Channels in the usage table are 1–8; chip IDs are 0 and 1.

## Scope and limitations

- YM2151 only, including dual-chip VGM commands. YM2610/YM2612 and other chips
  are not converted; files with no extractable YM2151 notes are rejected.
- Inputs are VGM/VGZ recordings, not ROM ZIPs. ROM recording is a separate step.
- Voices are snapshots at key-on. Parameter changes during notes, PCM, panning,
  LFO modulation, YM2151 noise, and layered arrangements are not reproduced.
  Active LFO modulation and noise are flagged in `voices.json`.
- Usage covers one pass through the file; loops are not repeated. First and last
  use refer to key-on timestamps, not note duration. Instrument roles are not
  inferred. Estimated pitches use KC/KF without chip-clock correction.
- Different LFO settings can produce separate source voices even though their
  converted static patches sound the same.
- Tested against the TX81Z software's MDX importer. Hardware playback has not
  been verified.
- Files are limited to 512 MiB after decompression. Unsupported commands and
  truncated streams produce errors.

## Validation

```sh
python3 -m unittest discover -s tests -v
```

The synthetic tests cover all 64 frequency codes and eight DT1 values, wait
commands, data blocks, dual chips, malformed streams, VGZ input, volume grouping,
and SysEx checksums. No game data is needed to run them.

During development, all 110 converted bytes matched the actual C++ MDX importer
for 1,024 randomized snapshots. The 17 extracted OutRun voices also matched the
previously auditioned TX81Z bank byte for byte. These external comparisons are
reported development checks, not part of the self-contained test suite.

## Related project

[vgm2x](https://github.com/vampirefrog/vgm2x) also extracts and deduplicates FM
voices, with broader chip support. vgm2syx focuses on TX81Z conversion and
cross-song usage reporting. It does not include code from vgm2x or libfmvoice.

## 日本語

VGM/VGZからYM2151の音色を取り出し、TX81Z用のSysExバンクに変換します。
複数曲をまとめて処理でき、どの音色がどの曲・チャンネル・時刻に使われるかも
一覧になります。ROM ZIPからのVGM作成や、PCM抽出は含みません。

```sh
python3 vgm2syx.py /path/to/VGMフォルダ -o /path/to/新しい出力先 --prefix GM
```

`bank_*.syx`をTX81Zソフトに読み込んでください。`source_*.mdx`で元音色を
確認でき、`usage.tsv`に曲との対応が出ます。変換方法はTX81ZソフトのMDX
変換に合わせています。音色の重ね合わせやLFO・ノイズは再現しません。

## License

MIT. This repository contains the converter and synthetic tests, without ROMs,
game recordings, or extracted game sound banks.
