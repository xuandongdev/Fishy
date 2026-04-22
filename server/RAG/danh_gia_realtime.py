import json
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV_PATH = Path("D:/Fishy/server/RAG/output/live_chat_metrics.csv")
DEFAULT_OUTPUT_DIR = SCRIPT_DIR / "output" / "bieu_do_realtime"

TIMING_COLUMNS = [
    "latency_ms",
    "retrieval_time_ms",
    "rerank_time_ms",
    "gen_time_ms",
]

COUNT_COLUMNS = [
    "source_count",
    "global_doc_hits",
    "legal_results",
    "candidate_results",
    "final_hits",
    "intent_match_count",
]

SCORE_COLUMNS = [
    "global_doc_top_score",
]

FLAG_COLUMNS = [
    "used_fallback",
    "answer_insufficient",
    "used_global_docs",
    "topic_mismatch",
    "retrieval_skipped",
]

DISPLAY_NAMES = {
    "latency_ms": "Latency",
    "retrieval_time_ms": "Retrieval",
    "rerank_time_ms": "Rerank",
    "gen_time_ms": "Generation",
    "source_count": "Source Count",
    "global_doc_hits": "Global Doc Hits",
    "legal_results": "Legal Results",
    "candidate_results": "Candidate Results",
    "final_hits": "Final Hits",
    "intent_match_count": "Intent Match Count",
    "global_doc_top_score": "Global Doc Top Score",
    "used_fallback": "Used Fallback",
    "answer_insufficient": "Answer Insufficient",
    "used_global_docs": "Used Global Docs",
    "topic_mismatch": "Topic Mismatch",
    "retrieval_skipped": "Retrieval Skipped",
}


def load_metrics(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        raise FileNotFoundError(f"Khong tim thay file CSV: {csv_path}")

    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    if df.empty:
        raise ValueError(f"File CSV dang rong: {csv_path}")

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    for column in TIMING_COLUMNS + COUNT_COLUMNS + SCORE_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    for column in FLAG_COLUMNS:
        if column in df.columns:
            df[column] = df[column].map(_to_bool)

    if "route" in df.columns:
        df["route"] = df["route"].fillna("unknown").astype(str)

    if "timestamp" in df.columns and df["timestamp"].notna().any():
        df = df.sort_values("timestamp").reset_index(drop=True)
    else:
        df = df.reset_index(drop=True)

    df["request_index"] = range(1, len(df) + 1)
    return df


def _to_bool(value) -> bool:
    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "on"}


def _available_columns(df: pd.DataFrame, columns: List[str]) -> List[str]:
    return [column for column in columns if column in df.columns]


def _safe_route_groups(df: pd.DataFrame) -> Optional[pd.core.groupby.generic.DataFrameGroupBy]:
    if "route" not in df.columns or df["route"].dropna().empty:
        return None
    return df.groupby("route", dropna=False)


def save_summary(df: pd.DataFrame, output_dir: Path) -> Path:
    summary: Dict[str, object] = {
        "rows": int(len(df)),
    }

    if "route" in df.columns:
        summary["routes"] = df["route"].value_counts(dropna=False).to_dict()

    for column in _available_columns(df, TIMING_COLUMNS + COUNT_COLUMNS + SCORE_COLUMNS):
        series = df[column].dropna()
        if series.empty:
            continue
        summary[column] = {
            "mean": round(float(series.mean()), 2),
            "median": round(float(series.median()), 2),
            "max": round(float(series.max()), 2),
            "p95": round(float(series.quantile(0.95)), 2),
        }

    for column in _available_columns(df, FLAG_COLUMNS):
        summary[column] = {
            "true_rate": round(float(df[column].fillna(False).mean() * 100.0), 2)
        }

    output_path = output_dir / "tom_tat_realtime.json"
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def plot_timing_overview(df: pd.DataFrame, output_dir: Path) -> Optional[Path]:
    columns = _available_columns(df, TIMING_COLUMNS)
    if not columns:
        return None

    stats = pd.DataFrame(
        {
            "Mean": [df[column].mean() for column in columns],
            "Median": [df[column].median() for column in columns],
            "P95": [df[column].quantile(0.95) for column in columns],
        },
        index=[DISPLAY_NAMES.get(column, column) for column in columns],
    )

    fig, ax = plt.subplots(figsize=(12, 6.5))
    stats.plot(kind="bar", ax=ax, color=["#1976d2", "#26a69a", "#ef6c00"], edgecolor="black")
    ax.set_title("Tong Quan Thoi Gian Xu Ly")
    ax.set_ylabel("Milliseconds (ms)")
    ax.set_xlabel("Chi so timing")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(title="Thong ke")
    annotate_bars(ax, decimals=1)
    fig.tight_layout()

    output_path = output_dir / "timing_overview.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_timing_trend(df: pd.DataFrame, output_dir: Path) -> Optional[Path]:
    columns = _available_columns(df, TIMING_COLUMNS)
    if not columns:
        return None

    fig, ax = plt.subplots(figsize=(13, 6.5))
    colors = ["#d32f2f", "#1976d2", "#388e3c", "#f9a825"]
    for color, column in zip(colors, columns):
        ax.plot(
            df["request_index"],
            df[column],
            marker="o",
            linewidth=2,
            markersize=4,
            label=DISPLAY_NAMES.get(column, column),
            color=color,
        )

    ax.set_title("Xu Huong Timing Theo Tung Request")
    ax.set_xlabel("Thu tu request")
    ax.set_ylabel("Milliseconds (ms)")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()

    output_path = output_dir / "timing_trend.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_timing_boxplot(df: pd.DataFrame, output_dir: Path) -> Optional[Path]:
    columns = _available_columns(df, TIMING_COLUMNS)
    if not columns:
        return None

    plot_df = df[columns].copy()
    plot_df.columns = [DISPLAY_NAMES.get(column, column) for column in columns]

    fig, ax = plt.subplots(figsize=(11, 6.5))
    bp = ax.boxplot([plot_df[column].dropna() for column in plot_df.columns], labels=plot_df.columns, patch_artist=True)
    for patch, color in zip(bp["boxes"], ["#90caf9", "#80cbc4", "#ffcc80", "#ef9a9a"]):
        patch.set_facecolor(color)
    ax.set_title("Phan Bo Timing Theo Request")
    ax.set_ylabel("Milliseconds (ms)")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()

    output_path = output_dir / "timing_distribution.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_hits_overview(df: pd.DataFrame, output_dir: Path) -> Optional[Path]:
    columns = _available_columns(df, COUNT_COLUMNS)
    if not columns:
        return None

    means = df[columns].mean().sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(12, 6.5))
    bars = ax.bar(
        [DISPLAY_NAMES.get(column, column) for column in means.index],
        means.values,
        color=["#1e88e5", "#43a047", "#fb8c00", "#8e24aa", "#00897b", "#e53935"],
        edgecolor="black",
    )
    ax.set_title("Gia Tri Trung Binh Cac Chi So Hits va Match")
    ax.set_ylabel("Gia tri trung binh")
    ax.set_xlabel("Chi so")
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(axis="x", rotation=15)
    annotate_bar_container(ax, bars, decimals=2)
    fig.tight_layout()

    output_path = output_dir / "hits_overview.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_hits_trend(df: pd.DataFrame, output_dir: Path) -> Optional[Path]:
    columns = _available_columns(df, ["legal_results", "candidate_results", "final_hits", "intent_match_count", "source_count"])
    if not columns:
        return None

    fig, ax = plt.subplots(figsize=(13, 6.5))
    colors = ["#3949ab", "#00897b", "#f4511e", "#8e24aa", "#6d4c41"]
    for color, column in zip(colors, columns):
        ax.plot(
            df["request_index"],
            df[column],
            marker="o",
            linewidth=2,
            markersize=4,
            label=DISPLAY_NAMES.get(column, column),
            color=color,
        )

    ax.set_title("Xu Huong Hits va Match Count Theo Request")
    ax.set_xlabel("Thu tu request")
    ax.set_ylabel("So luong")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()

    output_path = output_dir / "hits_trend.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_top_score(df: pd.DataFrame, output_dir: Path) -> Optional[Path]:
    columns = _available_columns(df, SCORE_COLUMNS)
    if not columns:
        return None

    column = columns[0]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.8))

    axes[0].plot(
        df["request_index"],
        df[column],
        marker="o",
        linewidth=2,
        color="#5e35b1",
    )
    axes[0].set_title("Top Score Theo Tung Request")
    axes[0].set_xlabel("Thu tu request")
    axes[0].set_ylabel("Score")
    axes[0].grid(alpha=0.25)

    axes[1].hist(df[column].dropna(), bins=min(10, max(5, len(df))), color="#7e57c2", edgecolor="black")
    axes[1].set_title("Phan Bo Global Doc Top Score")
    axes[1].set_xlabel("Score")
    axes[1].set_ylabel("Tan suat")
    axes[1].grid(axis="y", alpha=0.25)

    fig.tight_layout()
    output_path = output_dir / "top_score_analysis.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_flag_rates(df: pd.DataFrame, output_dir: Path) -> Optional[Path]:
    columns = _available_columns(df, FLAG_COLUMNS)
    if not columns:
        return None

    rates = (df[columns].fillna(False).mean() * 100.0).sort_values(ascending=False)

    fig, ax = plt.subplots(figsize=(11.5, 6.2))
    bars = ax.bar(
        [DISPLAY_NAMES.get(column, column) for column in rates.index],
        rates.values,
        color="#ff7043",
        edgecolor="black",
    )
    ax.set_title("Ti Le Xuat Hien Cac Trang Thai Live")
    ax.set_xlabel("Trang thai")
    ax.set_ylabel("Ti le (%)")
    ax.set_ylim(0, max(100, rates.max() * 1.2 if not rates.empty else 100))
    ax.grid(axis="y", alpha=0.25)
    ax.tick_params(axis="x", rotation=12)
    annotate_bar_container(ax, bars, decimals=1, suffix="%")
    fig.tight_layout()

    output_path = output_dir / "flag_rates.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def plot_route_breakdown(df: pd.DataFrame, output_dir: Path) -> Optional[Path]:
    route_groups = _safe_route_groups(df)
    if route_groups is None or route_groups.ngroups <= 1:
        return None

    timing_cols = _available_columns(df, TIMING_COLUMNS)
    hit_cols = _available_columns(df, ["final_hits", "intent_match_count", "source_count"])
    if not timing_cols and not hit_cols:
        return None

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    if timing_cols:
        route_groups[timing_cols].mean().plot(kind="bar", ax=axes[0], edgecolor="black")
        axes[0].set_title("Timing Trung Binh Theo Route")
        axes[0].set_xlabel("Route")
        axes[0].set_ylabel("Milliseconds (ms)")
        axes[0].grid(axis="y", alpha=0.25)
        axes[0].legend(fontsize=9)
    else:
        axes[0].axis("off")

    if hit_cols:
        route_groups[hit_cols].mean().plot(kind="bar", ax=axes[1], edgecolor="black")
        axes[1].set_title("Hits Trung Binh Theo Route")
        axes[1].set_xlabel("Route")
        axes[1].set_ylabel("Gia tri trung binh")
        axes[1].grid(axis="y", alpha=0.25)
        axes[1].legend(fontsize=9)
    else:
        axes[1].axis("off")

    fig.tight_layout()
    output_path = output_dir / "route_breakdown.png"
    fig.savefig(output_path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return output_path


def annotate_bars(ax, decimals: int = 2) -> None:
    for container in ax.containers:
        ax.bar_label(container, fmt=f"%.{decimals}f", padding=3, fontsize=8)


def annotate_bar_container(ax, bars, decimals: int = 2, suffix: str = "") -> None:
    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            f"{height:.{decimals}f}{suffix}",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )


def build_all_charts(csv_path: Path, output_dir: Path) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        plt.style.use("ggplot")

    df = load_metrics(csv_path)
    created_files: List[Path] = []

    summary_path = save_summary(df, output_dir)
    created_files.append(summary_path)

    for builder in [
        plot_timing_overview,
        plot_timing_trend,
        plot_timing_boxplot,
        plot_hits_overview,
        plot_hits_trend,
        plot_top_score,
        plot_flag_rates,
        plot_route_breakdown,
    ]:
        output_path = builder(df, output_dir)
        if output_path is not None:
            created_files.append(output_path)

    return created_files


def main() -> None:
    csv_path = DEFAULT_CSV_PATH
    output_dir = DEFAULT_OUTPUT_DIR
    created_files = build_all_charts(csv_path=csv_path, output_dir=output_dir)

    print(f"Da tao {len(created_files)} tep:")
    for path in created_files:
        print(f"- {path}")


if __name__ == "__main__":
    main()
