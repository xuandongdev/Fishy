import csv
import contextlib
import html
import io
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent


_CHART_BACKEND: Optional[str] = None
_CHART_BACKEND_ERROR: Optional[str] = None
_PLT = None
_SNS = None


DISPLAY_COLUMNS: List[Tuple[str, str]] = [
    ("query_id", "query_id"),
    ("gold_ids", "gold_id"),
    ("retrieved_ids", "retrieved_id"),
    ("first_relevant_rank", "first_relevant_rank"),
    ("hit_at_k", "hit_at_k"),
    ("recall_at_k", "recall_k"),
    ("mrr", "mrr"),
    ("context_precision", "context_precision"),
    ("context_recall", "context_recall"),
    ("faithfulness", "faithfulness"),
    ("answer_relevancy", "answer_relevancy"),
]

SUMMARY_METRICS: List[Tuple[str, str]] = [
    ("hit_at_k", "Hit@K"),
    ("recall_at_k", "Recall@K"),
    ("mrr", "MRR"),
    ("context_precision", "Context Precision"),
    ("context_recall", "Context Recall"),
    ("faithfulness", "Faithfulness"),
    ("answer_relevancy", "Answer Relevancy"),
]


RUN_CONFIG: Dict[str, str] = {
    # Sua cac gia tri nay roi chay: python server/RAG/bieu_do_dg.py
    "jsonl": "server/RAG/danh_gia_rag/danh_gia_060/rag_predictions_langchain2_t060_k5.jsonl",
    "csv": "server/RAG/danh_gia_rag/danh_gia_060/rag_evaluation_report_langchain2_t060_k5.csv",
    "out_dir": "server/RAG/danh_gia_rag/danh_gia_060/bieu_do_png",
    "base_name": "threshold_060_k5",
    "image_format": "png",
    "title": "Danh gia threshold 0.60 k=5",
}


def resolve_input_path(value: str) -> Optional[Path]:
    text = value.strip()
    if not text:
        return None

    raw_path = Path(text)
    if raw_path.is_absolute():
        return raw_path

    candidates = [
        PROJECT_ROOT / raw_path,
        Path.cwd() / raw_path,
        SCRIPT_DIR / raw_path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    return PROJECT_ROOT / raw_path


def resolve_output_path(value: str) -> Path:
    text = value.strip()
    if not text:
        raise ValueError("Gia tri duong dan output dang rong")

    raw_path = Path(text)
    if raw_path.is_absolute():
        return raw_path

    cwd_candidate = Path.cwd() / raw_path
    project_candidate = PROJECT_ROOT / raw_path
    script_candidate = SCRIPT_DIR / raw_path

    if project_candidate.exists():
        return project_candidate
    if cwd_candidate.exists():
        return cwd_candidate
    if script_candidate.exists():
        return script_candidate

    return project_candidate


def load_jsonl(path: Optional[Path]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if path is None or not path.exists():
        return items

    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line or line.startswith("//") or line.startswith("#"):
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL khong hop le o {path}, dong {line_no}: {exc.msg}") from exc
    return items


def parse_csv_value(value: str) -> Any:
    if value is None:
        return None

    text = value.strip()
    if text == "":
        return ""
    if text.lower() in {"nan", "none", "null"}:
        return None
    if text in {"True", "False"}:
        return text == "True"
    if text.startswith("[") and text.endswith("]"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    if re.fullmatch(r"-?\d+", text):
        try:
            return int(text)
        except ValueError:
            return text
    if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
        try:
            return float(text)
        except ValueError:
            return text
    return text


def load_csv_records(path: Optional[Path]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if path is None or not path.exists():
        return items

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            items.append({key: parse_csv_value(value) for key, value in row.items()})
    return items


def choose_merge_key(record_groups: Sequence[List[Dict[str, Any]]]) -> Optional[str]:
    for candidate in ("sample_key", "query_id"):
        if all(group and any(candidate in record for record in group) for group in record_groups):
            return candidate
    return None


def is_meaningful(value: Any) -> bool:
    if value is None:
        return False
    if value == "":
        return False
    if isinstance(value, list) and len(value) == 0:
        return False
    return True


def merge_record_values(target: Dict[str, Any], source: Dict[str, Any]) -> None:
    for key, value in source.items():
        if is_meaningful(value) or key not in target:
            target[key] = value


def merge_sources(json_records: List[Dict[str, Any]], csv_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    usable = [records for records in (json_records, csv_records) if records]
    if not usable:
        raise FileNotFoundError("Khong tim thay du lieu trong ca JSONL va CSV.")

    if len(usable) == 1:
        return [dict(record) for record in usable[0]]

    merge_key = choose_merge_key(usable)
    if not merge_key:
        merged = [dict(record) for record in csv_records]
        merged.extend(dict(record) for record in json_records)
        return merged

    merged_map: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for group in (csv_records, json_records):
        for record in group:
            key = record.get(merge_key)
            if key is None:
                continue
            key_text = str(key)
            if key_text not in merged_map:
                merged_map[key_text] = {}
                order.append(key_text)
            merge_record_values(merged_map[key_text], record)

    return [merged_map[key] for key in order]


def natural_sort_key(value: Any) -> List[Any]:
    text = "" if value is None else str(value)
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    try:
        text = str(value).strip()
        if text == "":
            return None
        return float(text)
    except ValueError:
        return None


def normalize_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for record in records:
        item = dict(record)
        if "recall_k" not in item and "recall_at_k" in item:
            item["recall_k"] = item["recall_at_k"]
        if "gold_id" not in item and "gold_ids" in item:
            item["gold_id"] = item["gold_ids"]
        if "retrieved_id" not in item and "retrieved_ids" in item:
            item["retrieved_id"] = item["retrieved_ids"]
        normalized.append(item)

    return sorted(normalized, key=lambda row: natural_sort_key(row.get("query_id")))


def format_list_like(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, tuple):
        return ", ".join(str(item) for item in value)
    return str(value)


def format_metric(value: Any) -> str:
    numeric = safe_float(value)
    if numeric is None:
        return ""
    return f"{numeric:.4f}"


def build_detail_rows(records: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for record in records:
        row: Dict[str, str] = {}
        for source_col, output_col in DISPLAY_COLUMNS:
            value = record.get(source_col)
            if source_col in {
                "first_relevant_rank",
                "hit_at_k",
                "recall_at_k",
                "recall_k",
                "mrr",
                "context_precision",
                "context_recall",
                "faithfulness",
                "answer_relevancy",
            }:
                row[output_col] = format_metric(value)
            else:
                row[output_col] = format_list_like(value)
        rows.append(row)
    return rows


def compute_summary(records: List[Dict[str, Any]]) -> Dict[str, float]:
    summary: Dict[str, float] = {}
    for column, _label in SUMMARY_METRICS:
        values = [safe_float(record.get(column)) for record in records]
        valid = [value for value in values if value is not None]
        if valid:
            summary[column] = sum(valid) / len(valid)
    return summary


def build_summary_series(
    summary: Dict[str, float],
    metric_columns: Sequence[Tuple[str, str]],
) -> List[Tuple[str, float]]:
    return [(label, summary[column]) for column, label in metric_columns if column in summary]


def card_html(title: str, value: str) -> str:
    return (
        '<div class="card">'
        f"<div class=\"card-title\">{html.escape(title)}</div>"
        f"<div class=\"card-value\">{html.escape(value)}</div>"
        "</div>"
    )


def build_summary_cards(records: List[Dict[str, Any]], summary: Dict[str, float]) -> str:
    hit_count = int(sum(safe_float(record.get("hit_at_k")) or 0.0 for record in records))
    miss_count = len(records) - hit_count
    cards = [
        card_html("Tong So Mau", str(len(records))),
        card_html("So Mau Hit", str(hit_count)),
        card_html("So Mau Miss", str(miss_count)),
    ]
    for column, label in SUMMARY_METRICS:
        if column in summary:
            cards.append(card_html(label, f"{summary[column]:.4f}"))
    return "".join(cards)


def build_rank_distribution(records: List[Dict[str, Any]]) -> List[Tuple[str, float]]:
    counts: Dict[str, float] = {}
    for record in records:
        rank = safe_float(record.get("first_relevant_rank"))
        if rank is None:
            counts["Miss"] = counts.get("Miss", 0.0) + 1.0
        else:
            label = f"Rank {int(rank)}"
            counts[label] = counts.get(label, 0.0) + 1.0

    ordered: List[Tuple[str, float]] = []
    rank_labels = sorted(
        (label for label in counts if label.startswith("Rank ")),
        key=lambda label: int(label.split(" ", 1)[1]),
    )
    for label in rank_labels:
        ordered.append((label, counts[label]))
    if "Miss" in counts:
        ordered.append(("Miss", counts["Miss"]))
    return ordered


def get_chart_backend() -> str:
    global _CHART_BACKEND
    global _CHART_BACKEND_ERROR
    global _PLT
    global _SNS

    if _CHART_BACKEND is not None:
        return _CHART_BACKEND

    stderr_buffer = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr_buffer):
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt_module
            import seaborn as sns_module

        _PLT = plt_module
        _SNS = sns_module
        _CHART_BACKEND = "seaborn"
        _CHART_BACKEND_ERROR = None
        return _CHART_BACKEND
    except Exception as exc:
        captured = stderr_buffer.getvalue()
        if "NumPy 1.x" in captured or "numpy.core.multiarray failed to import" in captured:
            _CHART_BACKEND_ERROR = "Matplotlib/Seaborn khong import duoc do xung dot NumPy trong environment hien tai"
        else:
            _CHART_BACKEND_ERROR = str(exc) or "Khong the import seaborn"
        _CHART_BACKEND = "pil"
        return _CHART_BACKEND


def maybe_report_chart_backend() -> None:
    backend = get_chart_backend()
    if backend != "seaborn" and _CHART_BACKEND_ERROR:
        print(f"Canh bao: khong the dung seaborn. Dang fallback ve PIL. Ly do: {_CHART_BACKEND_ERROR}")


def figure_to_image(fig: Any) -> Image.Image:
    if _PLT is None:
        raise RuntimeError("Matplotlib backend chua duoc khoi tao")

    buffer = io.BytesIO()
    try:
        fig.savefig(buffer, format="png", dpi=100, facecolor="white")
        buffer.seek(0)
        with Image.open(buffer) as image:
            return image.convert("RGB").copy()
    finally:
        _PLT.close(fig)


def build_empty_chart_image_seaborn(title: str, width: int, height: int) -> Image.Image:
    if _PLT is None or _SNS is None:
        raise RuntimeError("Seaborn backend chua duoc khoi tao")

    _SNS.set_theme(style="whitegrid")
    fig, ax = _PLT.subplots(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    ax.axis("off")
    ax.set_title(title, fontsize=22, fontweight="bold", color="#102a43", pad=16)
    ax.text(
        0.5,
        0.5,
        "Khong co du lieu de ve bieu do",
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=16,
        color="#334155",
        fontweight="bold",
    )
    fig.tight_layout()
    return figure_to_image(fig)


def build_bar_chart_image_seaborn(
    title: str,
    series: Sequence[Tuple[str, float]],
    *,
    width: int = 980,
    height: int = 360,
    max_value: Optional[float] = None,
    color: str = "#2563eb",
) -> Image.Image:
    if _PLT is None or _SNS is None:
        raise RuntimeError("Seaborn backend chua duoc khoi tao")

    if not series:
        return build_empty_chart_image_seaborn(title, width, height)

    _SNS.set_theme(style="whitegrid")
    labels = [label for label, _value in series]
    values = [max(0.0, float(value)) for _label, value in series]
    y_max = max_value if max_value is not None else max(values) if values else 1.0
    if y_max <= 0:
        y_max = 1.0
    plot_y_max = max(y_max * 1.12, max(values) * 1.18 if values else y_max)

    fig, ax = _PLT.subplots(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    _SNS.barplot(x=labels, y=values, color=color, ax=ax, saturation=1)

    ax.set_title(title, fontsize=22, fontweight="bold", color="#102a43", pad=12)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_ylim(0, plot_y_max)
    ticks = [y_max * tick / 5 for tick in range(6)]
    ax.set_yticks(ticks)
    ax.set_yticklabels([f"{tick:.2f}" for tick in ticks], color="#627d98")
    ax.tick_params(axis="x", labelsize=10, colors="#627d98", rotation=0)
    ax.tick_params(axis="y", labelsize=10, colors="#627d98")
    ax.grid(axis="y", color="#e7edf3")
    ax.grid(axis="x", visible=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#bcccdc")
    ax.spines["bottom"].set_color("#bcccdc")

    for patch, value in zip(ax.patches, values):
        ax.text(
            patch.get_x() + patch.get_width() / 2,
            value + plot_y_max * 0.02,
            f"{value:.4f}",
            ha="center",
            va="bottom",
            fontsize=10,
            fontweight="bold",
            color="#102a43",
        )

    fig.tight_layout()
    return figure_to_image(fig)


def build_metric_line_chart_image_seaborn(
    title: str,
    records: List[Dict[str, Any]],
    metric_columns: Sequence[Tuple[str, str]],
    *,
    width: int = 980,
    height: int = 360,
) -> Image.Image:
    if _PLT is None or _SNS is None:
        raise RuntimeError("Seaborn backend chua duoc khoi tao")

    if not records:
        return build_empty_chart_image_seaborn(title, width, height)

    usable_metrics = [
        (column, label)
        for column, label in metric_columns
        if any(safe_float(record.get(column)) is not None for record in records)
    ]
    if not usable_metrics:
        return build_empty_chart_image_seaborn(title, width, height)

    _SNS.set_theme(style="whitegrid")
    fig, ax = _PLT.subplots(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_facecolor("#ffffff")
    ax.set_facecolor("#ffffff")
    colors = ["#ef4444", "#2563eb", "#10b981", "#f59e0b"]
    n = len(records)

    for metric_idx, (column, label) in enumerate(usable_metrics):
        x_values: List[int] = []
        y_values: List[float] = []
        for idx, record in enumerate(records):
            value = safe_float(record.get(column))
            if value is None:
                continue
            x_values.append(idx)
            y_values.append(value)
        if not y_values:
            continue
        _SNS.lineplot(
            x=x_values,
            y=y_values,
            marker="o",
            linewidth=2.5,
            markersize=6,
            color=colors[metric_idx % len(colors)],
            label=label,
            ax=ax,
        )

    step = max(1, math.ceil(n / 10))
    tick_positions = list(range(0, n, step))
    if tick_positions[-1] != n - 1:
        tick_positions.append(n - 1)

    ax.set_title(title, fontsize=22, fontweight="bold", color="#102a43", pad=12)
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax.set_ylim(0, 1.02)
    ax.set_yticks([tick / 5 for tick in range(6)])
    ax.set_yticklabels([f"{tick / 5:.1f}" for tick in range(6)], color="#627d98")
    ax.set_xticks(tick_positions)
    ax.set_xticklabels(
        [str(records[idx].get("query_id", idx + 1)) for idx in tick_positions],
        rotation=0,
        fontsize=8,
        color="#627d98",
    )
    ax.grid(axis="y", color="#e7edf3")
    ax.grid(axis="x", visible=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#bcccdc")
    ax.spines["bottom"].set_color("#bcccdc")
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.2),
        ncol=min(4, len(usable_metrics)),
        frameon=False,
        fontsize=10,
    )

    fig.subplots_adjust(bottom=0.27)
    fig.tight_layout()
    return figure_to_image(fig)


def load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    center_x: float,
    y: float,
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    width, height = text_size(draw, text, font)
    draw.text((center_x - width / 2, y), text, font=font, fill=fill)


def build_bar_chart_image(
    title: str,
    series: Sequence[Tuple[str, float]],
    *,
    width: int = 980,
    height: int = 360,
    max_value: Optional[float] = None,
    color: str = "#2563eb",
) -> Image.Image:
    if get_chart_backend() == "seaborn":
        return build_bar_chart_image_seaborn(
            title,
            series,
            width=width,
            height=height,
            max_value=max_value,
            color=color,
        )

    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    title_font = load_font(24, bold=True)
    label_font = load_font(12)
    value_font = load_font(12, bold=True)

    if not series:
        draw_centered_text(draw, width / 2, height / 2 - 8, "Khong co du lieu de ve bieu do", title_font, "#334155")
        return image

    values = [max(0.0, float(value)) for _label, value in series]
    y_max = max_value if max_value is not None else max(values) if values else 1.0
    if y_max <= 0:
        y_max = 1.0

    left = 72
    right = 24
    top = 52
    bottom = 88
    plot_width = width - left - right
    plot_height = height - top - bottom
    slot = plot_width / max(len(series), 1)
    bar_width = min(54.0, slot * 0.55)

    draw_centered_text(draw, width / 2, 14, title, title_font, "#102a43")

    for tick in range(6):
        tick_value = y_max * tick / 5
        y = top + plot_height - (plot_height * tick / 5)
        draw.line([(left, y), (width - right, y)], fill="#e7edf3", width=1)
        tick_text = f"{tick_value:.2f}"
        tw, th = text_size(draw, tick_text, label_font)
        draw.text((left - tw - 12, y - th / 2), tick_text, font=label_font, fill="#627d98")

    draw.line([(left, top + plot_height), (width - right, top + plot_height)], fill="#bcccdc", width=2)

    for idx, (label, value) in enumerate(series):
        x = left + idx * slot + (slot - bar_width) / 2
        bar_height = 0.0 if y_max == 0 else (float(value) / y_max) * plot_height
        y = top + plot_height - bar_height
        draw.rounded_rectangle(
            [(x, y), (x + bar_width, top + plot_height)],
            radius=6,
            fill=color,
        )
        value_text = f"{float(value):.4f}"
        draw_centered_text(draw, x + bar_width / 2, y - 18, value_text, value_font, "#102a43")
        draw_centered_text(draw, x + bar_width / 2, height - 46, label, label_font, "#627d98")

    return image


def build_metric_line_chart_image(
    title: str,
    records: List[Dict[str, Any]],
    metric_columns: Sequence[Tuple[str, str]],
    *,
    width: int = 980,
    height: int = 360,
) -> Image.Image:
    if get_chart_backend() == "seaborn":
        return build_metric_line_chart_image_seaborn(
            title,
            records,
            metric_columns,
            width=width,
            height=height,
        )

    image = Image.new("RGB", (width, height), "#ffffff")
    draw = ImageDraw.Draw(image)
    title_font = load_font(24, bold=True)
    label_font = load_font(12)
    legend_font = load_font(13)

    if not records:
        draw_centered_text(draw, width / 2, height / 2 - 8, "Khong co du lieu de ve bieu do", title_font, "#334155")
        return image

    colors = ["#ef4444", "#2563eb", "#10b981", "#f59e0b"]
    left = 72
    right = 24
    top = 52
    bottom = 82
    plot_width = width - left - right
    plot_height = height - top - bottom
    n = len(records)
    usable_metrics = [
        (column, label)
        for column, label in metric_columns
        if any(safe_float(record.get(column)) is not None for record in records)
    ]

    draw_centered_text(draw, width / 2, 14, title, title_font, "#102a43")

    for tick in range(6):
        tick_value = tick / 5
        y = top + plot_height - (plot_height * tick / 5)
        draw.line([(left, y), (width - right, y)], fill="#e7edf3", width=1)
        tick_text = f"{tick_value:.1f}"
        tw, th = text_size(draw, tick_text, label_font)
        draw.text((left - tw - 12, y - th / 2), tick_text, font=label_font, fill="#627d98")

    draw.line([(left, top + plot_height), (width - right, top + plot_height)], fill="#bcccdc", width=2)

    for metric_idx, (column, _label) in enumerate(usable_metrics):
        points: List[Tuple[float, float]] = []
        color = colors[metric_idx % len(colors)]
        for idx, record in enumerate(records):
            value = safe_float(record.get(column))
            if value is None:
                continue
            x = left if n == 1 else left + (idx / (n - 1)) * plot_width
            y = top + plot_height - value * plot_height
            points.append((x, y))
        if len(points) >= 2:
            draw.line(points, fill=color, width=3)
        for x, y in points:
            draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=color)

    step = max(1, math.ceil(n / 10))
    for idx in range(0, n, step):
        x = left if n == 1 else left + (idx / (n - 1)) * plot_width
        label = str(records[idx].get("query_id", idx + 1))
        draw_centered_text(draw, x, height - 36, label, label_font, "#627d98")

    legend_y = height - 14
    legend_x = left
    for metric_idx, (_column, label) in enumerate(usable_metrics):
        color = colors[metric_idx % len(colors)]
        x = legend_x + metric_idx * 180
        draw.ellipse((x - 5, legend_y - 5, x + 5, legend_y + 5), fill=color)
        draw.text((x + 12, legend_y - 8), label, font=legend_font, fill="#627d98")

    return image


def make_output_stem(base_name: str, jsonl_path: Optional[Path], csv_path: Optional[Path]) -> str:
    if base_name:
        return base_name
    if jsonl_path is not None and jsonl_path.exists():
        return jsonl_path.stem
    if csv_path is not None and csv_path.exists():
        return csv_path.stem
    return "danh_gia_rag"


def write_image(path: Path, image: Image.Image, image_format: str) -> None:
    save_format = "JPEG" if image_format.lower() in {"jpg", "jpeg"} else image_format.upper()
    image.save(path, format=save_format)


def write_summary_csv(path: Path, summary: Dict[str, float]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["metric_key", "metric_label", "mean_value"])
        writer.writeheader()
        for column, label in SUMMARY_METRICS:
            if column in summary:
                writer.writerow(
                    {
                        "metric_key": column,
                        "metric_label": label,
                        "mean_value": f"{summary[column]:.6f}",
                    }
                )


def write_detail_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    headers = [header for _source, header in DISPLAY_COLUMNS]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    jsonl_value = RUN_CONFIG.get("jsonl", "").strip()
    csv_value = RUN_CONFIG.get("csv", "").strip()
    out_dir_value = RUN_CONFIG.get("out_dir", "").strip()
    base_name = RUN_CONFIG.get("base_name", "").strip()
    image_ext = RUN_CONFIG.get("image_format", "png").strip().lower() or "png"
    title_prefix = RUN_CONFIG.get("title", "").strip()

    jsonl_path = resolve_input_path(jsonl_value) if jsonl_value else None
    csv_path = resolve_input_path(csv_value) if csv_value else None
    if not out_dir_value:
        raise ValueError("RUN_CONFIG['out_dir'] dang rong. Hay dat thu muc output trong file.")

    out_dir = resolve_output_path(out_dir_value)
    out_dir.mkdir(parents=True, exist_ok=True)
    output_stem = make_output_stem(base_name, jsonl_path, csv_path)

    json_records = load_jsonl(jsonl_path)
    csv_records = load_csv_records(csv_path)
    if not json_records and not csv_records:
        raise FileNotFoundError("Khong tim thay du lieu hop le. Hay sua RUN_CONFIG['jsonl'] hoac RUN_CONFIG['csv'].")

    merged_records = normalize_records(merge_sources(json_records, csv_records))
    detail_rows = build_detail_rows(merged_records)
    summary = compute_summary(merged_records)
    maybe_report_chart_backend()

    retrieval_title = "Trung Binh Metric Retrieval"
    quality_title = "Trung Binh Metric Chat Luong"
    rank_title = "Phan Bo First Relevant Rank"
    retrieval_query_title = "Retrieval Theo Tung Query"
    quality_query_title = "Chat Luong Theo Tung Query"

    if title_prefix:
        retrieval_title = f"{title_prefix} - {retrieval_title}"
        quality_title = f"{title_prefix} - {quality_title}"
        rank_title = f"{title_prefix} - {rank_title}"
        retrieval_query_title = f"{title_prefix} - {retrieval_query_title}"
        quality_query_title = f"{title_prefix} - {quality_query_title}"

    retrieval_summary_chart = build_bar_chart_image(
        retrieval_title,
        build_summary_series(
            summary,
            [
                ("hit_at_k", "Hit@K"),
                ("recall_at_k", "Recall@K"),
                ("mrr", "MRR"),
            ],
        ),
        max_value=1.0,
        color="#0f766e",
    )
    quality_summary_chart = build_bar_chart_image(
        quality_title,
        build_summary_series(
            summary,
            [
                ("context_precision", "Context Precision"),
                ("context_recall", "Context Recall"),
                ("faithfulness", "Faithfulness"),
                ("answer_relevancy", "Answer Relevancy"),
            ],
        ),
        max_value=1.0,
        color="#ea580c",
    )
    rank_chart = build_bar_chart_image(
        rank_title,
        build_rank_distribution(merged_records),
        color="#7c3aed",
    )
    retrieval_trend_chart = build_metric_line_chart_image(
        retrieval_query_title,
        merged_records,
        [
            ("hit_at_k", "Hit@K"),
            ("recall_at_k", "Recall@K"),
            ("mrr", "MRR"),
        ],
    )
    quality_trend_chart = build_metric_line_chart_image(
        quality_query_title,
        merged_records,
        [
            ("context_precision", "Context Precision"),
            ("context_recall", "Context Recall"),
            ("faithfulness", "Faithfulness"),
            ("answer_relevancy", "Answer Relevancy"),
        ],
    )

    detail_csv_path = out_dir / f"{output_stem}_bang_chi_tiet.csv"
    summary_csv_path = out_dir / f"{output_stem}_tong_hop_metric.csv"
    retrieval_summary_image_path = out_dir / f"{output_stem}_retrieval_summary.{image_ext}"
    quality_summary_image_path = out_dir / f"{output_stem}_quality_summary.{image_ext}"
    rank_image_path = out_dir / f"{output_stem}_first_relevant_rank_distribution.{image_ext}"
    retrieval_trend_image_path = out_dir / f"{output_stem}_retrieval_by_query.{image_ext}"
    quality_trend_image_path = out_dir / f"{output_stem}_quality_by_query.{image_ext}"

    write_detail_csv(detail_csv_path, detail_rows)
    write_summary_csv(summary_csv_path, summary)
    write_image(retrieval_summary_image_path, retrieval_summary_chart, image_ext)
    write_image(quality_summary_image_path, quality_summary_chart, image_ext)
    write_image(rank_image_path, rank_chart, image_ext)
    write_image(retrieval_trend_image_path, retrieval_trend_chart, image_ext)
    write_image(quality_trend_image_path, quality_trend_chart, image_ext)

    print(f"Da ghi CSV chi tiet: {detail_csv_path}")
    print(f"Da ghi CSV tong hop: {summary_csv_path}")
    print(f"Da ghi bieu do: {retrieval_summary_image_path}")
    print(f"Da ghi bieu do: {quality_summary_image_path}")
    print(f"Da ghi bieu do: {rank_image_path}")
    print(f"Da ghi bieu do: {retrieval_trend_image_path}")
    print(f"Da ghi bieu do: {quality_trend_image_path}")


if __name__ == "__main__":
    main()
