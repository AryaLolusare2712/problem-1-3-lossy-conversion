from __future__ import annotations
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from analyzer import scan_directory, aggregate_report, write_csv


def main():
    parser = argparse.ArgumentParser(description="Metadata-driven video lossy-conversion ROI estimator")
    parser.add_argument("--input", required=True, help="Directory containing the video corpus")
    parser.add_argument("--output", default="report.json", help="Output JSON report")
    parser.add_argument("--metadata-csv", default="metadata.csv", help="Output probed metadata CSV")
    parser.add_argument("--size-ratio", type=float, default=0.55,
                        help="Expected encoded size / original size (must be measured on a sample)")
    parser.add_argument("--encode-speed", type=float, default=1.5,
                        help="Encoded media seconds per wall-clock second")
    parser.add_argument("--io-seconds-per-gb", type=float, default=8.0)
    parser.add_argument("--vlm-passes", type=int, default=1,
                        help="Expected future full reads / captioning passes")
    parser.add_argument("--storage-cost-per-gb-month", type=float, default=0.02)
    parser.add_argument("--retention-months", type=int, default=1)
    args = parser.parse_args()

    metadata = scan_directory(args.input)
    if not metadata:
        raise SystemExit("No readable videos found. Check the path and install FFmpeg/ffprobe.")
    write_csv(metadata, args.metadata_csv)
    report = aggregate_report(
        metadata,
        expected_size_ratio=args.size_ratio,
        conversion_speed_factor=args.encode_speed,
        io_seconds_per_gb=args.io_seconds_per_gb,
        vlm_passes=args.vlm_passes,
        storage_cost_per_gb_month=args.storage_cost_per_gb_month,
        retention_months=args.retention_months,
    )
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "videos"}, indent=2))
    print(f"\nWrote {args.metadata_csv} and {args.output}")


if __name__ == "__main__":
    main()
