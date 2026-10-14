import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from analyzer import VideoMetadata, recommend_conversion, aggregate_report


def test_recommendation_contains_break_even_fields():
    meta = VideoMetadata("large.mov", 2_000_000_000, 3600, 1920, 1080, 30, 0, "prores", "mov", True)
    result = recommend_conversion(meta, expected_size_ratio=0.5, conversion_speed_factor=2, io_seconds_per_gb=30, vlm_passes=3)
    assert result["estimated_conversion_seconds"] == 1800
    assert result["estimated_io_seconds_saved"] == 90
    assert result["net_time_saved_seconds"] == -1710
    assert result["decision"] == "keep_original"


def test_aggregate_report_counts():
    items = [
        VideoMetadata("a.mov", 2_000_000_000, 3600, 1920, 1080, 30, 0, "prores", "mov", True),
        VideoMetadata("b.mp4", 100_000_000, 600, 1280, 720, 30, 0, "h264", "mov", True),
    ]
    report = aggregate_report(items)
    assert report["video_count"] == 2
    assert report["keep_original_count"] + report["compress_count"] == 2
