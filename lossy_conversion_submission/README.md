# Task 3 — Lossy Conversion ROI Estimator

Metadata-driven utility to decide whether incoming videos are worth re-encoding before VLM captioning.

## Requirements
- Python 3.10+
- FFmpeg/ffprobe installed and on PATH (for metadata probing)
- Python packages: `pip install -r requirements.txt`

## Run
```bash
python src/main.py --input /path/to/video_corpus --output report.json --metadata-csv metadata.csv
```

Tune assumptions using measurements from your infrastructure:
```bash
python src/main.py --input ./videos --size-ratio 0.45 --encode-speed 2.0 --io-seconds-per-gb 12 --vlm-passes 4 --storage-cost-per-gb-month 0.02 --retention-months 6
```

`--size-ratio` is compressed size/original size; `--encode-speed` is media seconds encoded per wall-clock second. Outputs include per-video decisions and aggregate estimated time savings. Estimates are not benchmarks.

## Tests
```bash
pip install pytest
python -m pytest tests -v
```

See [`docs/design.md`](docs/design.md) for the decision model, codec trade-offs, benchmarking plan, and limitations.
