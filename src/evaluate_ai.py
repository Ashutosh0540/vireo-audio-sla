"""Create a review sample or measure agreement with supplied review labels. No API calls."""

import argparse
from pathlib import Path

import pandas as pd

from ai_reasons import REASONS

ROOT = Path(__file__).resolve().parents[1]
# Scoring remains compatible with the original text-only evaluation CSV.
BASE_EVAL_COLUMNS = [
    "ticket_id", "customer_message", "agent_notes", "ai_reason",
    "ai_confidence", "ai_evidence", "human_reason", "agreement", "review_notes",
]
CONTEXT_COLUMNS = [
    "channel", "response_minutes", "sla_minutes", "created_shift",
    "overnight_created", "transfers", "assigned_team",
]
EVAL_COLUMNS = BASE_EVAL_COLUMNS[:3] + CONTEXT_COLUMNS + BASE_EVAL_COLUMNS[3:]


def read_csv(path, required):
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(f"{path}: missing columns: {', '.join(sorted(missing))}")
    return frame


def create_sample(source, size=30):
    if size < 1:
        raise ValueError("Sample size must be positive")
    confidence = pd.to_numeric(source["ai_confidence"], errors="coerce")
    successful = source.loc[
        source["ai_error"].fillna("").str.strip().eq("")
        & source["ai_reason"].isin(REASONS)
        & confidence.between(0, 1)
        & source["ai_evidence"].fillna("").str.strip().ne("")
    ].drop_duplicates("ticket_id")
    if len(successful) < size:
        raise ValueError(
            f"Need {size} successful unique classifications; found {len(successful)}. "
            "Classify a larger sample first; API failures cannot be human-evaluation cases."
        )

    # Approximately proportional allocation, with at least one per available
    # category when size permits. Fixed seed makes selection reproducible.
    counts = successful["ai_reason"].value_counts().sort_index()
    quotas = counts * size / len(successful)
    allocated = pd.Series(0, index=counts.index)
    if size >= len(counts):
        allocated[:] = 1
    while allocated.sum() < size:
        available = allocated < counts
        reason = (quotas - allocated)[available].idxmax()
        allocated[reason] += 1
    sample = pd.concat([
        successful.loc[successful["ai_reason"].eq(reason)].sample(n=int(n), random_state=42)
        for reason, n in allocated.items() if n > 0
    ]).sample(frac=1, random_state=42).copy()
    for column in ("human_reason", "agreement", "review_notes"):
        sample[column] = ""
    return sample[EVAL_COLUMNS].reset_index(drop=True)


def evaluate(frame):
    if frame["ticket_id"].str.strip().eq("").any() or frame["ticket_id"].duplicated().any():
        raise ValueError("Evaluation ticket IDs must be nonempty and unique")
    frame = frame.copy()
    frame["human_reason"] = frame["human_reason"].fillna("").str.strip()
    if not frame["ai_reason"].isin(REASONS).all():
        raise ValueError("Every evaluation row must have a successful, valid AI reason")
    invalid = frame.loc[
        frame["human_reason"].ne("") & ~frame["human_reason"].isin(REASONS), "human_reason"
    ].unique()
    if len(invalid):
        raise ValueError(f"Invalid human_reason labels: {', '.join(invalid)}. Use the exact taxonomy names.")

    reviewed = frame.loc[frame["human_reason"].ne("")]
    matches = reviewed["human_reason"].eq(reviewed["ai_reason"])
    size = len(reviewed)
    agreements = int(matches.sum())
    frame["agreement"] = ""
    frame.loc[reviewed.index, "agreement"] = matches.map({True: "yes", False: "no"})

    print("Review-label agreement\n----------------------")
    print("Agreement is consistency with supplied labels, not an independent model accuracy estimate.")
    assistant_labels = int(reviewed["review_notes"].fillna("").str.startswith("Assistant-reviewed:").sum())
    if assistant_labels:
        print(f"Label provenance: {assistant_labels}/{size} assistant-generated review labels.")
    print("Errors below mean label disagreements, not independently established classification errors.")
    print(f"Rows in evaluation file: {len(frame)}")
    print(f"Sample size: {size}")
    print(f"Unlabeled tickets: {len(frame) - size}")
    if not size:
        print("Pending manual labels; agreement and error rates are not yet available.")
        return frame
    if size < len(frame):
        print("Partial evaluation: metrics below use labeled tickets only.")
    print(f"Agreement: {agreements}/{size}")
    print(f"Agreement rate: {agreements / size:.2%}")
    print(f"Errors: {size - agreements}")
    print(f"Error rate: {(size - agreements) / size:.2%}")

    disagreements = reviewed.loc[~matches]
    print("\nMost common disagreements (human reason -> AI reason):")
    if disagreements.empty:
        print("None")
    else:
        patterns = disagreements.groupby(["human_reason", "ai_reason"]).size().sort_values(ascending=False)
        for (human, ai), count in patterns.items():
            print(f"{human} -> {ai}: {count}")
    print("\nConfusion matrix (rows = human reason, columns = AI reason):")
    print(pd.crosstab(reviewed["human_reason"], reviewed["ai_reason"]).to_string())
    return frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-sample", action="store_true", help="Create a blank human-review CSV instead of scoring")
    parser.add_argument("--source", type=Path, default=ROOT / "output" / "ai_reason_sample.csv")
    parser.add_argument("--file", type=Path, default=ROOT / "output" / "ai_human_eval_30.csv")
    parser.add_argument("--sample", type=int, default=30, help="Number of tickets when creating a sample")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing review sample (erases labels)")
    args = parser.parse_args()
    try:
        if args.create_sample:
            if args.file.exists() and not args.overwrite:
                raise ValueError(f"{args.file} already exists. Use --overwrite only if you intend to discard its labels.")
            source = read_csv(args.source, BASE_EVAL_COLUMNS[:6] + CONTEXT_COLUMNS + ["ai_error"])
            sample = create_sample(source, args.sample)
            args.file.parent.mkdir(parents=True, exist_ok=True)
            sample.to_csv(args.file, index=False)
            print(f"Human evaluation sample created: {len(sample)}")
            print(f"Source: {args.source}")
            print(sample["ai_reason"].value_counts().to_string())
            print(f"Saved to: {args.file}")
        else:
            frame = read_csv(args.file, BASE_EVAL_COLUMNS)
            evaluated = evaluate(frame)
            evaluated.to_csv(args.file, index=False)
            print(f"Saved computed agreement column to: {args.file}")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
