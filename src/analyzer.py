"""Metadata-driven video compression decision and ROI estimator.

Uses only Python stdlib for analysis. Optional FFmpeg integration is documented
in the design note; estimates are scenario-based until measured on the target host.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import csv
import json
import math
import subprocess
import time
from typing import Iterable

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mpeg", ".mpg"}

@dataclass
class VideoMetadata:
    path: str
    size_bytes: int
    duration_seconds: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    bitrate_bps: float = 0.0
    codec: str = "unknown"
    format_name: str = "unknown"
    has_audio: bool = False

    @property
    def megapixels(self) -> float:
        return self.width * self.height / 1_000_000 if self.width and self.height else 0.0

    @property
    def size_mb(self) -> float:
        return self.size_bytes / 1_000_000

    @property
    def mb_per_minute(self) -> float:
        return self.size_mb / (self.duration_seconds / 60) if self.duration_seconds > 0 else 0.0


def probe_video(path: str) -> VideoMetadata:
    """Probe a video using ffprobe. Requires FFmpeg installed and on PATH."""
    p = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration,size,bit_rate,format_name:stream=codec_type,codec_name,width,height,r_frame_rate",
         "-of", "json", path],
        capture_output=True, text=True, check=True
    )
    data = json.loads(p.stdout)
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = any(s.get("codec_type") == "audio" for s in streams)
    fps = 0.0
    rate = video.get("r_frame_rate", "0/1")
    try:
        n, d = rate.split("/")
        fps = float(n) / float(d) if float(d) else 0.0
    except (ValueError, ZeroDivisionError):
        pass
    return VideoMetadata(
        path=path,
        size_bytes=int(fmt.get("size") or Path(path).stat().st_size),
        duration_seconds=float(fmt.get("duration") or 0),
        width=int(video.get("width") or 0),
        height=int(video.get("height") or 0),
        fps=fps,
        bitrate_bps=float(fmt.get("bit_rate") or 0),
        codec=video.get("codec_name", "unknown"),
        format_name=fmt.get("format_name", "unknown"),
        has_audio=audio,
    )


def scan_directory(root: str) -> list[VideoMetadata]:
    """Recursively scan known video extensions; unreadable files are skipped."""
    results = []
    for path in Path(root).rglob("*"):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            try:
                results.append(probe_video(str(path)))
            except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError, OSError):
                continue
    return results


def recommend_conversion(
    meta: VideoMetadata,
    *,
    target_codec: str = "h264",
    target_container: str = "mp4",
    expected_size_ratio: float = 0.55,
    conversion_speed_factor: float = 1.5,
    io_seconds_per_gb: float = 8.0,
    vlm_passes: int = 1,
    storage_cost_per_gb_month: float = 0.02,
    retention_months: int = 1,
    require_quality_check: bool = True,
) -> dict:
    """Estimate break-even with explicit, adjustable assumptions.

    conversion_speed_factor = encoded media seconds / wall-clock second.
    Expected size ratio is a hypothesis to validate with a sample benchmark.
    """
    size_gb = meta.size_bytes / 1_000_000_000
    target_size_gb = size_gb * expected_size_ratio
    saved_gb = max(0.0, size_gb - target_size_gb)
    duration = max(0.0, meta.duration_seconds)
    conversion_seconds = duration / max(0.01, conversion_speed_factor)
    io_saved_per_pass_seconds = saved_gb * io_seconds_per_gb
    io_saved_seconds = io_saved_per_pass_seconds * max(0, vlm_passes)
    storage_saved_cost = saved_gb * storage_cost_per_gb_month * max(0, retention_months)
    # time ROI is a separate operational metric; dollar ROI includes storage only
    # unless user supplies their own compute/IO hourly rate.
    net_time_seconds = io_saved_seconds - conversion_seconds
    # Without a user-supplied encoding price, make the primary decision on measured-time break-even.
    # Storage savings are reported separately and can justify compression in a cost-aware deployment.
    worthwhile = net_time_seconds > 0
    # Avoid converting already efficient/low-bitrate media blindly.
    if meta.size_bytes <= 0 or duration <= 0:
        worthwhile = False
    if meta.codec.lower() in {"h264", "avc1", "hevc", "h265", "av1", "vp9"} and meta.mb_per_minute < 80:
        worthwhile = False
    return {
        "path": meta.path,
        "input_size_gb": round(size_gb, 6),
        "estimated_output_size_gb": round(target_size_gb, 6),
        "estimated_size_reduction_percent": round((1 - expected_size_ratio) * 100, 2),
        "saved_gb": round(saved_gb, 6),
        "estimated_conversion_seconds": round(conversion_seconds, 2),
        "estimated_io_seconds_saved": round(io_saved_seconds, 2),
        "net_time_saved_seconds": round(net_time_seconds, 2),
        "estimated_storage_savings": round(storage_saved_cost, 6),
        "target": f"{target_container}/{target_codec}",
        "decision": "compress" if worthwhile else "keep_original",
        "assumptions": {
            "expected_size_ratio": expected_size_ratio,
            "conversion_speed_factor": conversion_speed_factor,
            "io_seconds_per_gb": io_seconds_per_gb,
            "vlm_passes": vlm_passes,
            "storage_cost_per_gb_month": storage_cost_per_gb_month,
            "retention_months": retention_months,
            "quality_validation_required": require_quality_check,
        },
        "caveat": "Estimate only; benchmark sample encodes and validate caption quality before production."
    }


def aggregate_report(metadata: Iterable[VideoMetadata], **kwargs) -> dict:
    items = [recommend_conversion(m, **kwargs) for m in metadata]
    total_input = sum(i["input_size_gb"] for i in items)
    total_output = sum(i["estimated_output_size_gb"] for i in items)
    total_convert = sum(i["estimated_conversion_seconds"] for i in items if i["decision"] == "compress")
    total_io_saved = sum(i["estimated_io_seconds_saved"] for i in items if i["decision"] == "compress")
    compressed = [i for i in items if i["decision"] == "compress"]
    return {
        "video_count": len(items),
        "compress_count": len(compressed),
        "keep_original_count": len(items) - len(compressed),
        "input_size_gb": round(total_input, 6),
        "estimated_output_size_gb_if_all_compressed": round(total_output, 6),
        "estimated_conversion_seconds_for_recommended": round(total_convert, 2),
        "estimated_io_seconds_saved_for_recommended": round(total_io_saved, 2),
        "net_time_saved_seconds": round(total_io_saved - total_convert, 2),
        "videos": items,
    }


def write_csv(metadata: Iterable[VideoMetadata], output_path: str) -> None:
    rows = [asdict(m) | {"size_mb": round(m.size_mb, 3), "mb_per_minute": round(m.mb_per_minute, 3)}
            for m in metadata]
    if not rows:
        Path(output_path).write_text("", encoding="utf-8")
        return
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
