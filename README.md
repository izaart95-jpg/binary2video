<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=35&pause=1000&color=1A1A1A&center=true&vCenter=true&width=800&height=70&lines=BINARY2VIDEO" alt="BINARY2VIDEO" />

**Pack any file into an ordinary, playable video and pull it back out byte-for-byte. The payload rides in RGB pixel frames plus PCM audio tracks, coded lossless with ffmpeg.**

---

</div>

## 📦 Usage

Needs `python3` and `ffmpeg`, nothing else.

```sh
./binary2video [-f fps] [-w width] [-h height] [-c png|vp9|h264|ffv1|ffv1l3] [-m ch] [-t tracks] [-n] [-v] infile outfile
./video2binary [-v] outfile restored_file
```

```sh
./binary2video -n -c png backup.tar data.mkv            # default — densest
./binary2video -n -t 4 -m 8 -f 25 data.bin data.mkv     # 1 MiB in 0.12 s of video
./binary2video -c h264 -w 1280 -h 720 data.bin data.mkv # player-friendly big frames
./binary2video -n -c vp9 data.bin data.webm             # the browser one (video only)
./video2binary -v data.mkv data.out
```

The outfile extension picks the container: `.mkv .nut .avi` accept every codec, `.mp4 .mov` take png/h264, `.webm` takes vp9 only and stays video-only (webm doesn't admit lossless audio).

| flag | meaning |
|------|---------|
| `-m` | audio channels, 1..8 (6 = 5.1 surround, 8 = 7.1) |
| `-t` | audio tracks, 1..8 — capacity = t × m × 96 kB/s stacked on the video |
| `-n` | skip gzip — for already-compressed data or plain noise |
| `-v` | show the payload header, the track split and MD5s |
| `-f -w -h -c` | framerate, resolution, codec — same as the bash prototype |

## 🎬 Storage format

One video frame is W×H rgb24 pixels = `W*H*3` payload bytes, one byte per channel. The first frame opens with a 54-byte ASCII header:

```
B2V3r0000000010485760000000006911360000000003574400804
     ^ flag(r raw / z gzip)                channels=08, tracks=04
       ^ 1048576 B original file
         ^ 691136 B through the video track
           ^ 357440 B spread over the audio tracks
```

Then the payload follows, and both sides share it so video seconds and audio seconds match — minimum length for the data, maximum bytes per second. The video track is fed raw RGB pixels at `fps*w*h*3` B/s; each audio track is 48 kHz mono PCM, 96 kB/s flat. At high fps video alone outruns every audio lane and the packer stops using audio quietly.

Peek at a real one:

```sh
ffmpeg -i data.mkv -f rawvideo -pix_fmt rgb24 - | head -c 54
```

video2binary still decodes every format this project went through: the original gzip+padding scheme, the interim `B2V1` video-only header, the `B2V2` mono single-track header, and the current `B2V3`. A corrupt header (payload shorter than it claims) is rejected instead of silently truncated.

## 📊 Numbers (1 MiB of /dev/urandom → 320x240 .mkv)

Codecs:

| codec | output | note |
|-------|--------|------|
| png (default) | 1.05 MiB / 3.72 s | densest — deflate passes noise ~1:1 |
| vp9 lossless | 1.10 MiB | webm's only codec |
| ffv1 / ffv1l3 | 1.12 / 1.22 MiB | fastest, slices = parallel |
| h264 CABAC qp0 | 1.38 MiB | friendliest bitstream, greediest size |

Audio configurations (same file, png codec — file stays ~1.05 MiB, duration drops):

| audio | duration | payload rate |
|-------|----------|--------------|
| none (video only) | 5.00 s | 230 kB/s |
| mono, 1 track | 3.72 s | 326 kB/s |
| 5.1 (6 ch) | 1.42 s | 806 kB/s |
| 4 tracks × 5.1 | 1.00 s | 2.53 MB/s |
| 4 × 7.1 @ 25 fps | 0.12 s | ~8.8 MB/s |

The first bash prototype (h264 ultrafast qp0, video track only) stored the same 1 MiB in ~1.6 MiB of video, an 8-byte input at 5.8 kB — now 3.0 kB at 720p, 1.3 kB at defaults. Every codec/container/track/channel pair here was roundtripped and md5-verified.

Honest caveat: this is storage, not steganography — play a packed file and you get RGB noise frames and loud static. It's a valid video any player will open, but anyone sniffing metadata will know it isn't a cat video.

## 🛈 Modes

Default mode: maximum density, bit-exact through any lossless carrier. If the
video is only going to travel as a file — copy, chat attachment that you send
as a document — this is the one to use.

## 🛡️ YouTube-proof mode `-y` (format B2V4)

When the video must go *through* a transcoding platform (YouTube, messengers,
editors), byte-exact pixels die — measured on a real YouTube roundtrip: the
platform re-encoded 4:4:4 → lossy 4:2:0, re-timed one frame into 18, and
smudged the payload region, while every *flat* area came back bit-for-bit.
`-y` stores data the way transcoders can't destroy:

- payload bytes → **big flat gray cells** (R = G = B): survives chroma
  subsampling and every RGB↔YUV matrix (gray is identical in all of them)
- one **calibration ramp** row per frame → cells are classified by *nearest
  ramp level*, so any monotonic brightness shift (gamma, range, codec qp)
  cancels out
- a **frame-index row** → duplicates dedupe, reorders self-heal — because
  platforms re-time everything
- the whole stream underneath **Reed–Solomon GF(256)** (159 data + 64 parity
  per block = 32 corrupted bytes repairable per block) and **block-interleaved**
  across every frame — a lost or garbled frame costs a few bytes per block
  instead of whole blocks. gzip still optional
- carrier: plain H.264 yuv420p `.mp4`/`.mov` with a silent AAC track, x264
  adaptive quantization off (it smears flat gray cells) and crf picked per
  palette: 4 gray levels → crf 38, 8 → crf 33

Verified against simulated platform transcodes: H.264 crf 23 and a bitrate-
starved crf 33, VP9, AV1, 6 fps re-timing, and a 33→36-frame full shuffle
with duplicate inserts — all bit-exact after decode. At 1 MiB scale the
harsh corner (carrier re-encoded again at crf 23 with default settings)
survives too: ~12x RS headroom at 320p, ~43x at 720p.

```sh
./binary2video -y data.bin data.mp4                # the uploadable one
./binary2video -y -f 30 data.bin data.mp4          # ~3.7 kB/s instead of 125 B/s
./binary2video -y --levels 8 data.bin data.mp4     # denser, tighter margins
video2binary data.mp4 data.out                     # same tool, auto-detected
```

The price is honest: ~125 bytes of payload per 320x240 frame (after RS), so
kilobytes-per-minute territory. Resolution barely shrinks the file (the
codec pays per cell and the cell count follows the payload), but it scales
the payload rate hard — same 1 MiB, levels 4, 30 fps, measured:

| -y at levels 4 | output | duration | payload rate |
|---|---|---|---|
| 320p | 16.3 MB | 4.7 min | ~3.8 kB/s |
| 720p | 15.5 MB | 22 s | ~48 kB/s |
| FHD | 15.4 MB | 9.7 s | ~109 kB/s |
| 4K | 15.1 MB | 2.4 s | ~440 kB/s |

All four survive the harsh re-encode gate (Widest margins at FHD and above —
the re-encode gets tons of bitrate to work with). For files of 10+ MiB,
4K packs ~440 kB/s so even a 10 MiB file is a 24-second upload.
`--levels 8` fits more per frame (a 6-second 12.6 MB FHD carrier for 1 MiB)
but its tight spacing fails the harsh gate even at FHD — compact-but-risky
route only. `--levels 2` doubles the safety margin for flaky platforms.

To verify with your own platform: pack, upload, redownload the best quality,
then `./video2binary redownloaded.mp4 out.bin` — MD5 must match.

## 🔧 Ideas on the table

- FLAC payload audio to give `.webm` a second slot (ffmpeg's webm muxer refuses flac today: "Only VP8 or VP9 or AV1 video and Vorbis or Opus audio")
- 4K/60fps is ~1.5 GB/s of packing on paper — no one has to write new code for it, just `-w 3840 -h 2160 -f 60`
- AV1 lossless via gray planes worked for density (~0.5x) but did NOT roundtrip bit-exact — ffmpeg's pixel conversions eat bytes, so it stays out on purpose
- 4 bits/cell (`--levels 16`) measured dead for the platform route: the carrier itself can be pristine (crf 22 packs a FHD MiB into 13.5 MB bit-exact) but one real platform pass smears the 12-level spacing past the RS budget. Spacing *is* the margin — the market here stays {2, 4, 8} levels
- pre-blurred carriers (`boxblur=2:1`): smoother cell edges make the codec only ~7% cheaper per cell, and blur leaks into the sampled cell cores — repair load went from ~0 to 27,771 bytes per MiB. Redesign cell/sample geometry before revisiting
- audio channel as a second data lane: tone-based watermarks that survive platform transcodes run in bits-per-second — a whole video's audio carries a few hundred bytes. Worthless next to the video lane; silence stays
