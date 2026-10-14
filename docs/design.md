# Task 3 — Metadata-driven lossy video conversion

## Executive decision

Do **not** re-encode every incoming video. Probe metadata first, estimate the break-even point, and benchmark a representative sample. Keep the original as the source of truth. For files that pass the gate, create a derived captioning copy using **MP4 + H.264 (libx264), CRF 23, preset `veryfast`, and `yuv420p`** as a conservative baseline. Compare with **H.265/HEVC** only when storage/I/O dominates and the extra encoding cost is justified. AV1 can yield smaller files but often costs more CPU time to encode; do not choose it without measurements on the deployment hardware.

These are starting points, not universal winners. For mostly static scenes, text-heavy slides, small objects, or visual fine detail, compression artifacts may change captions. Run quality validation on the actual Qwen3-VL prompt/task before adopting any setting. Retain originals when forensic, archival, or pixel-level use is required.

## Decision model

Use `ffprobe` metadata: byte size, duration, dimensions, FPS, codec, container, bitrate and audio stream. Derive:
- MB/minute = file size in MB / duration in minutes
- resolution class and codec generation
- estimated output size from a measured sample encode, not a hard-coded universal ratio
- estimated conversion time from measured encode speed on the target host

Let:
- `S` = original size in GB
- `r` = compressed/original size ratio (measured)
- `v` = encode speed in media-seconds per wall-second
- `D` = video duration in seconds
- `p` = expected future full-read/captioning passes
- `t_io` = seconds per GB of I/O on the real storage path
- `c_s` = storage price per GB-month and `m` = retention months

Then:
- output size = `S*r`
- bytes saved = `S*(1-r)`
- conversion wall time = `D/v`
- I/O time saved = `S*(1-r)*t_io*p`
- time break-even: compress only if `S*(1-r)*t_io*p > D/v` (include upload/download/network I/O if relevant)
- storage benefit = `S*(1-r)*c_s*m`
- monetary ROI must include actual compute cost of encoding, storage cost, and any billed transfer/read cost. Do not equate seconds saved with dollars without a measured price for those seconds.

The CLI reports estimates per file and in aggregate. Its defaults are illustrative assumptions and must be replaced with local measurements. The estimator conservatively keeps already-efficient modern-codec videos under 80 MB/minute. That threshold is a heuristic; calibrate it on corpus percentiles and actual read cost.

## Metadata-based policy

1. **Keep original only**: invalid/short metadata, already efficient H.264/H.265/VP9/AV1 at modest MB/minute, low expected reuse, short duration, or conversion cost exceeds I/O savings.
2. **Candidate for compression**: unusually high MB/minute, older/intra-frame codecs (e.g. ProRes, DNxHR, MJPEG), uncompressed sources, large high-resolution files, and repeated VLM reads. Still benchmark before converting.
3. **Quality-sensitive exception**: keep originals and use a lossless or high-quality derivative for OCR, small text, tiny objects, fine-grained action recognition, evidence/medical/scientific footage, or any workflow requiring exact pixels.
4. **Avoid redundant work**: store an idempotent derivative keyed by source hash + encoder settings; never re-encode a previously generated derivative.

## Formats and trade-offs

| Format/codec | Typical trade-off | Recommendation |
|---|---|---|
| MP4 + H.264/AVC | Broad hardware/software support, fast decoding, moderate size | Default compatibility baseline |
| MP4 + H.265/HEVC | Often smaller at comparable subjective quality; slower encoding and sometimes less convenient decoding | Test for high-volume storage-bound corpora |
| MP4/WebM + AV1 | Often better compression efficiency; encode can be slow depending on encoder/hardware | Consider only after measured ROI |
| WebM + VP9 | Good web delivery efficiency; CPU and decoder performance vary | Benchmark if already in use |
| ProRes/DNxHR/MJPEG input | Editing-friendly/intra-frame/high bitrate, often large | Strong compression candidate if captioning tolerates re-encode |
| GIF | Inefficient for long/high-quality video; limited color | Convert only if needed for compatibility, not as a quality-preserving master |

Container is not the same as codec. Changing `.mov` to `.mp4` without re-encoding may be a remux, which can save time but usually does not reduce video payload size significantly.

## Benchmark protocol (required before production)

1. Stratify sample by input codec, resolution, FPS, duration, MB/minute and content type.
2. Encode samples with H.264 CRF 20/23/26 and, optionally, HEVC CRF 24/28 and AV1 with a suitable quality setting. Record output bytes and wall time.
3. Compare captions from Qwen3-VL on original and compressed clips with the same frames/prompts. Score key-object retention, OCR/text, action/event fidelity, hallucination rate and human-rated semantic agreement.
4. Choose the smallest file that passes the agreed caption-quality threshold, not simply the smallest file.
5. Recalculate break-even with measured `r`, `v`, storage throughput, expected reuse, and cloud price. Roll out gradually and monitor.

Example FFmpeg baseline:
```bash
ffmpeg -i input.mov -c:v libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -c:a aac -b:a 96k output.mp4
```
If audio is irrelevant to the VLM pipeline, consider dropping it (`-an`) only after confirming no speech/audio questions depend on it.

## Limits and honest reporting

No actual corpus measurements or Qwen3-VL inference were run by this repository alone. The CLI probes local files and estimates ROI; size ratio, encoder speed, I/O throughput, VLM passes and storage prices are inputs/assumptions. A final recommendation must be based on real sample encodes and caption-quality checks.
