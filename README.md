<div align="center">

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=35&pause=1000&color=1A1A1A&center=true&vCenter=true&width=800&height=70&lines=BINARY2VIDEO" alt="BINARY2VIDEO" />

**Pack any file into an ordinary, playable video and pull it back out byte-for-byte. The payload rides in RGB pixel frames plus a PCM audio track, coded lossless with ffmpeg.**

---

</div>

## 📦 Usage

Needs `python3` and `ffmpeg`, nothing else.

```sh
./binary2video [-f fps] [-w width] [-h height] [-c png|vp9|h264|ffv1|ffv1l3] [-n] [-v] infile outfile
./video2binary [-v] outfile restored_file
```

```sh
./binary2video -n -c png backup.tar data.mkv            # default — densest
./binary2video -c h264 -w 1280 -h 720 data.bin data.mkv # player-friendly big frames
./binary2video -n -c vp9 data.bin data.webm             # the browser one (video only)
./video2binary -v data.mkv data.out
```

The outfile extension picks the container: `.mkv .nut .avi` accept every codec, `.mp4 .mov` take png/h264, `.webm` takes vp9 only and stays video-only (webm doesn't admit lossless audio).

| flag | meaning |
|------|---------|
| `-n` | skip gzip — for already-compressed data or plain noise |
| `-v` | show the payload header, the video/audio split and MD5s |
| `-f -w -h -c` | framerate, resolution, codec — same command line as the bash prototype |

## 🎬 Storage format

One frame is W×H rgb24 pixels = `W*H*3` payload bytes, one byte per channel. The first frame opens with a 50-byte ASCII header:

```
B2V2r000000001048576000000000691150000000000357426
     ^ flag(r raw / z gzip)
       ^ 1048576 B original file
         ^ 691150 B through the video track
           ^ 357426 B through the audio track
```

Then the payload follows, and both tracks share it so video and audio play for the same duration — minimum length for the data, maximum bytes per second. The video track is fed raw RGB pixels at `fps*w*h*3` B/s; the audio track is 48 kHz mono s16le samples, a flat 96 kB/s of capacity on top. At high fps video alone outruns the audio channel and the packer quietly stops using it.

Peek at a real one:

```sh
ffmpeg -i data.mkv -f rawvideo -pix_fmt rgb24 - | head -c 50
```

video2binary also still understands the two older formats this project went through: the original gzip+padding scheme and an interim `B2V1` video-only header.

## 📊 Numbers (1 MiB of /dev/urandom → 320x240 .mkv)

| codec | output | note |
|-------|--------|------|
| png (default) | 1.05 MiB / 3.72 s | densest — deflate passes noise ~1:1 |
| vp9 lossless | 1.10 MiB | webm's only codec |
| ffv1 / ffv1l3 | 1.12 / 1.22 MiB | fastest, slices = parallel |
| h264 CABAC qp0 | 1.38 MiB | friendliest bitstream, greediest size |

For comparison, the first bash prototype (h264 ultrafast qp0, video track only) stored the same 1 MiB in ~1.6 MiB of video. An 8-byte input went from 5.8 kB (720p) to 1.3 kB at defaults. Every codec/container pair here was roundtripped and md5-verified — png@1 byte-per-channel paths included.

Honest caveat: this is storage, not steganography — play a packed file and you get RGB noise frames and loud static. It's a valid video any player will open, but anyone sniffing metadata will know it isn't a cat video.

## 🔧 Ideas on the table

- 5.1-channel audio (~576 kB/s each) or several audio tracks in one container
- FLAC payload audio to give `.webm` a second slot
- 4K/60fps: one frame is ~25 MB — 1.5 GB/s of packing on paper
