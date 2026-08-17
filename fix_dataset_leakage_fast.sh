#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/oualid/Desktop/Data_mission/RL_Agent"

TRAIN="$ROOT/data/processed/train_processed.csv"
TEST="$ROOT/data/processed/test_processed.csv"

INC_TRAIN="$ROOT/data/rl_incident/train_incident.csv"
INC_TEST="$ROOT/data/rl_incident/test_incident.csv"

WORK="$ROOT/.leakage_fix_tmp"
CHUNK=50000

echo "============================================================"
echo "FIX DATASET LEAKAGE — NO BACKUP"
echo "============================================================"
echo "ROOT : $ROOT"
echo "TRAIN: $TRAIN"
echo "TEST : $TEST"
echo "CHUNK: $CHUNK"
echo
echo "RULE:"
echo "  TEST incidents are authoritative."
echo "  All overlapping TRAIN incidents are removed."
echo "  Exact duplicate TEST rows are removed."
echo
echo "NO BACKUP WILL BE CREATED."
echo "============================================================"

[[ -f "$TRAIN" ]] || { echo "ERROR: missing $TRAIN"; exit 1; }
[[ -f "$TEST" ]] || { echo "ERROR: missing $TEST"; exit 1; }
[[ -f "$INC_TRAIN" ]] || { echo "ERROR: missing $INC_TRAIN"; exit 1; }
[[ -f "$INC_TEST" ]] || { echo "ERROR: missing $INC_TEST"; exit 1; }

rm -rf "$WORK"
mkdir -p "$WORK"

export TRAIN TEST INC_TRAIN INC_TEST WORK CHUNK

python3 - <<'PY'
import csv
import hashlib
import os
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

TRAIN = Path(os.environ["TRAIN"])
TEST = Path(os.environ["TEST"])
INC_TRAIN = Path(os.environ["INC_TRAIN"])
INC_TEST = Path(os.environ["INC_TEST"])
WORK = Path(os.environ["WORK"])
CHUNK = int(os.environ["CHUNK"])


# ============================================================
# HELPERS
# ============================================================

def header(path):
    with path.open(
        "r",
        encoding="utf-8-sig",
        errors="replace",
        newline=""
    ) as f:
        return next(csv.reader(f))


def count_rows(path):
    with path.open(
        "r",
        encoding="utf-8",
        errors="replace",
        newline=""
    ) as f:
        return max(0, sum(1 for _ in f) - 1)


def row_digest(row):
    h = hashlib.blake2b(digest_size=16)

    for value in row:
        b = str(value).encode(
            "utf-8",
            errors="replace"
        )
        h.update(
            len(b).to_bytes(8, "little")
        )
        h.update(b)

    return h.digest()


# ============================================================
# READ SCHEMAS
# ============================================================

TRAIN_COLUMNS = header(TRAIN)
TEST_COLUMNS = header(TEST)

if TRAIN_COLUMNS != TEST_COLUMNS:
    raise RuntimeError(
        "TRAIN and TEST processed schemas differ."
    )

if "IncidentId" not in TRAIN_COLUMNS:
    raise RuntimeError(
        "IncidentId is missing."
    )

if "AlertId" not in TRAIN_COLUMNS:
    raise RuntimeError(
        "AlertId is missing."
    )

INC_TRAIN_COLUMNS = header(INC_TRAIN)
INC_TEST_COLUMNS = header(INC_TEST)

if "IncidentId" not in INC_TRAIN_COLUMNS:
    raise RuntimeError(
        "IncidentId missing from incident_Train."
    )

if "IncidentId" not in INC_TEST_COLUMNS:
    raise RuntimeError(
        "IncidentId missing from incident_Test."
    )

if "IncidentAlertCount" not in INC_TRAIN_COLUMNS:
    raise RuntimeError(
        "IncidentAlertCount missing from incident_Train."
    )

if "IncidentAlertCount" not in INC_TEST_COLUMNS:
    raise RuntimeError(
        "IncidentAlertCount missing from incident_Test."
    )


# ============================================================
# STEP 1
# TEST INCIDENT SET
#
# 236k IDs fits comfortably in RAM.
# ============================================================

print()
print("============================================================")
print("STEP 1 — LOAD TEST INCIDENT IDs")
print("============================================================")

test_incidents = set()

test_incident_file = WORK / "test_incidents.txt"

with TEST.open(
    "r",
    encoding="utf-8-sig",
    errors="replace",
    newline=""
) as f, test_incident_file.open(
    "w",
    encoding="utf-8"
) as out:

    reader = csv.DictReader(f)

    for row in reader:
        incident = str(
            row["IncidentId"]
        )

        test_incidents.add(incident)
        out.write(incident + "\n")

print(
    f"TEST unique IncidentId: {len(test_incidents):,}"
)


# ============================================================
# STEP 2
# CLEAN TEST EXACT DUPLICATES
#
# Only the duplicate fingerprint set is kept in RAM.
# The dataset itself is streamed.
# ============================================================

print()
print("============================================================")
print("STEP 2 — REMOVE EXACT DUPLICATE TEST ROWS")
print("============================================================")

clean_test = WORK / "test_processed.clean.csv"

seen_hashes = set()
duplicate_incident_counts = Counter()

test_rows = 0
test_kept = 0
test_duplicates = 0

reader = pd.read_csv(
    TEST,
    dtype=str,
    keep_default_na=False,
    na_filter=False,
    chunksize=CHUNK,
    low_memory=True
)

first_write = True

for chunk_number, chunk in enumerate(
    reader,
    start=1
):

    chunk = chunk[TEST_COLUMNS]

    output_rows = []

    for row in chunk.itertuples(
        index=False,
        name=None
    ):

        test_rows += 1

        digest = row_digest(row)

        if digest in seen_hashes:

            test_duplicates += 1

            incident = str(row[0])

            duplicate_incident_counts[
                incident
            ] += 1

            continue

        seen_hashes.add(digest)

        output_rows.append(row)
        test_kept += 1

    if output_rows:

        out_df = pd.DataFrame.from_records(
            output_rows,
            columns=TEST_COLUMNS
        )

        out_df.to_csv(
            clean_test,
            mode="w" if first_write else "a",
            header=first_write,
            index=False,
            lineterminator="\n"
        )

        first_write = False

    print(
        f"[TEST] "
        f"chunk={chunk_number:,} "
        f"seen={test_rows:,} "
        f"kept={test_kept:,} "
        f"duplicates={test_duplicates:,}",
        flush=True
    )

if test_duplicates != 4:
    print(
        f"WARNING: expected 4 exact duplicates, "
        f"found {test_duplicates}."
    )

print()
print(
    f"TEST original : {test_rows:,}"
)
print(
    f"TEST kept     : {test_kept:,}"
)
print(
    f"TEST removed   : {test_duplicates:,}"
)


# ============================================================
# STEP 3
# REMOVE TRAIN ALERTS FROM TEST INCIDENTS
# ============================================================

print()
print("============================================================")
print("STEP 3 — REMOVE TRAIN/TEST INCIDENT OVERLAP")
print("============================================================")

clean_train = WORK / "train_processed.clean.csv"

train_rows = 0
train_kept = 0
train_removed = 0
removed_incidents = set()

reader = pd.read_csv(
    TRAIN,
    dtype=str,
    keep_default_na=False,
    na_filter=False,
    chunksize=CHUNK,
    low_memory=True
)

first_write = True

for chunk_number, chunk in enumerate(
    reader,
    start=1
):

    chunk = chunk[TRAIN_COLUMNS]

    mask = ~chunk["IncidentId"].astype(str).isin(
        test_incidents
    )

    removed_chunk = chunk.loc[~mask]

    if not removed_chunk.empty:

        train_removed += len(
            removed_chunk
        )

        removed_incidents.update(
            removed_chunk["IncidentId"]
            .astype(str)
            .unique()
        )

    kept_chunk = chunk.loc[mask]

    if not kept_chunk.empty:

        kept_chunk.to_csv(
            clean_train,
            mode="w" if first_write else "a",
            header=first_write,
            index=False,
            lineterminator="\n"
        )

        first_write = False

        train_kept += len(
            kept_chunk
        )

    train_rows += len(chunk)

    print(
        f"[TRAIN] "
        f"chunk={chunk_number:,} "
        f"seen={train_rows:,} "
        f"kept={train_kept:,} "
        f"removed={train_removed:,}",
        flush=True
    )

print()
print(
    f"TRAIN original : {train_rows:,}"
)
print(
    f"TRAIN kept     : {train_kept:,}"
)
print(
    f"TRAIN removed  : {train_removed:,}"
)
print(
    f"TRAIN incidents removed: "
    f"{len(removed_incidents):,}"
)


# ============================================================
# STEP 4
# CLEAN INCIDENT TRAIN
#
# Remove incidents that were removed from alert-level TRAIN.
# ============================================================

print()
print("============================================================")
print("STEP 4 — UPDATE incident_Train.csv")
print("============================================================")

clean_inc_train = WORK / "incident_Train.clean.csv"

incident_train_rows = 0
incident_train_kept = 0

with INC_TRAIN.open(
    "r",
    encoding="utf-8-sig",
    errors="replace",
    newline=""
) as fin, clean_inc_train.open(
    "w",
    encoding="utf-8",
    newline=""
) as fout:

    reader = csv.DictReader(fin)

    writer = csv.DictWriter(
        fout,
        fieldnames=INC_TRAIN_COLUMNS
    )

    writer.writeheader()

    for row in reader:

        incident_train_rows += 1

        incident = str(
            row["IncidentId"]
        )

        if incident in test_incidents:
            continue

        writer.writerow(row)
        incident_train_kept += 1

print(
    f"incident_Train original: "
    f"{incident_train_rows:,}"
)

print(
    f"incident_Train kept: "
    f"{incident_train_kept:,}"
)


# ============================================================
# STEP 5
# UPDATE incident_Test.csv COUNTS
#
# The 4 exact duplicate alert rows were removed from TEST.
# Reduce IncidentAlertCount for the affected incidents.
# ============================================================

print()
print("============================================================")
print("STEP 5 — UPDATE incident_Test.csv COUNTS")
print("============================================================")

clean_inc_test = WORK / "incident_Test.clean.csv"

incident_test_rows = 0
incident_test_kept = 0
incident_counts_changed = 0

with INC_TEST.open(
    "r",
    encoding="utf-8-sig",
    errors="replace",
    newline=""
) as fin, clean_inc_test.open(
    "w",
    encoding="utf-8",
    newline=""
) as fout:

    reader = csv.DictReader(fin)

    writer = csv.DictWriter(
        fout,
        fieldnames=INC_TEST_COLUMNS
    )

    writer.writeheader()

    for row in reader:

        incident_test_rows += 1

        incident = str(
            row["IncidentId"]
        )

        removed_count = duplicate_incident_counts.get(
            incident,
            0
        )

        if removed_count:
            old_count = int(
                row["IncidentAlertCount"]
            )

            new_count = old_count - removed_count

            if new_count < 1:
                raise RuntimeError(
                    f"IncidentAlertCount would become "
                    f"{new_count} for {incident}"
                )

            row["IncidentAlertCount"] = str(
                new_count
            )

            incident_counts_changed += 1

        writer.writerow(row)
        incident_test_kept += 1

print(
    f"incident_Test rows: "
    f"{incident_test_kept:,}"
)

print(
    f"Incident counts adjusted: "
    f"{incident_counts_changed:,}"
)


# ============================================================
# STEP 6
# VERIFY BEFORE REPLACEMENT
# ============================================================

print()
print("============================================================")
print("STEP 6 — VERIFY CLEAN FILES")
print("============================================================")


# ---- TEST exact uniqueness ----

seen = set()
test_exact_duplicates_after = 0

with clean_test.open(
    "r",
    encoding="utf-8-sig",
    errors="replace",
    newline=""
) as f:

    reader = csv.DictReader(f)

    for row in reader:

        values = tuple(
            row[c]
            for c in TEST_COLUMNS
        )

        digest = row_digest(values)

        if digest in seen:
            test_exact_duplicates_after += 1
        else:
            seen.add(digest)


if test_exact_duplicates_after != 0:
    raise RuntimeError(
        "TEST still contains exact duplicate rows."
    )


# ---- Incident overlap after filtering ----

test_incident_check = set()

with clean_test.open(
    "r",
    encoding="utf-8-sig",
    errors="replace",
    newline=""
) as f:

    reader = csv.DictReader(f)

    for row in reader:
        test_incident_check.add(
            str(row["IncidentId"])
        )

overlap_after = 0

with clean_train.open(
    "r",
    encoding="utf-8-sig",
    errors="replace",
    newline=""
) as f:

    reader = csv.DictReader(f)

    for row in reader:

        if str(row["IncidentId"]) in test_incident_check:
            overlap_after += 1

if overlap_after != 0:
    raise RuntimeError(
        f"TRAIN/TEST incident leakage remains: "
        f"{overlap_after} rows"
    )


# ---- Counts ----

clean_train_rows = count_rows(clean_train)
clean_test_rows = count_rows(clean_test)
clean_inc_train_rows = count_rows(clean_inc_train)
clean_inc_test_rows = count_rows(clean_inc_test)

print()
print(
    f"Clean TRAIN rows       : "
    f"{clean_train_rows:,}"
)

print(
    f"Clean TEST rows        : "
    f"{clean_test_rows:,}"
)

print(
    f"Clean incident TRAIN   : "
    f"{clean_inc_train_rows:,}"
)

print(
    f"Clean incident TEST    : "
    f"{clean_inc_test_rows:,}"
)

print(
    f"Exact TEST duplicates  : "
    f"{test_exact_duplicates_after}"
)

print(
    f"Incident overlap       : "
    f"{overlap_after}"
)


# ============================================================
# STEP 7
# ATOMIC REPLACEMENT
#
# No backup.
# Existing files are replaced only after verification.
# ============================================================

print()
print("============================================================")
print("STEP 7 — REPLACE DATASETS")
print("============================================================")

replacements = [
    (
        clean_train,
        TRAIN
    ),
    (
        clean_test,
        TEST
    ),
    (
        clean_inc_train,
        INC_TRAIN
    ),
    (
        clean_inc_test,
        INC_TEST
    ),
]

for source, destination in replacements:

    os.replace(
        source,
        destination
    )

    print(
        f"[REPLACED] {destination}"
    )


# ============================================================
# STEP 8
# FINAL HEALTH NUMBERS
# ============================================================

print()
print("============================================================")
print("STEP 8 — FINAL HEALTH")
print("============================================================")

final_train_rows = count_rows(TRAIN)
final_test_rows = count_rows(TEST)
final_inc_train_rows = count_rows(INC_TRAIN)
final_inc_test_rows = count_rows(INC_TEST)

print(
    f"TRAIN rows          : "
    f"{final_train_rows:,}"
)

print(
    f"TEST rows           : "
    f"{final_test_rows:,}"
)

print(
    f"TRAIN incidents     : "
    f"{final_inc_train_rows:,}"
)

print(
    f"TEST incidents      : "
    f"{final_inc_test_rows:,}"
)

print()
print("EXACT TEST DUPLICATES : 0")
print("TRAIN/TEST INCIDENT   : 0")
print()
print("============================================================")
print("SUCCESS")
print("============================================================")
print()
print("No backup created.")
print("Original files replaced in-place.")
print("RAM-safe chunked processing.")
print("============================================================")

PY

echo
echo "============================================================"
echo "CLEANUP"
echo "============================================================"

rm -rf "$WORK"

echo "[OK] temporary files removed."

echo
echo "============================================================"
echo "DONE"
echo "============================================================"

exit 0
