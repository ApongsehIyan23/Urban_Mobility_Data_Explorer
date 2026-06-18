#!/usr/bin/env bash

# Exit on undefined variables and pipe failures
set -u
set -o pipefail

DOWNLOAD_DIR="data/raw"

# List of files
FILES=(
   
    #January to December 2025 Yellow Taxi Trip Data
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet"
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-02.parquet"
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-03.parquet"
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-04.parquet"
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-05.parquet"
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-06.parquet"
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-07.parquet"
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-08.parquet"
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-09.parquet"
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-10.parquet"
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-11.parquet"
    "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-12.parquet"

    # Taxi Zone Lookup Table (CSV)
    "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"

    # Taxi Zone Spatial Metadata (Parquet)
    "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zones.zip"
)

# 1. Dependency & Environment Checks
for cmd in curl awk tail tr wc df; do
    if ! command -v "$cmd" &> /dev/null; then
        echo "[FATAL] Required command '$cmd' is not installed." >&2
        exit 1
    fi
done

if ! mkdir -p "$DOWNLOAD_DIR" 2>/dev/null; then
    echo "[FATAL] Cannot create directory '$DOWNLOAD_DIR'. Check permissions." >&2
    exit 1
fi

if [ ! -w "$DOWNLOAD_DIR" ]; then
    echo "[FATAL] Directory '$DOWNLOAD_DIR' is not writable." >&2
    exit 1
fi

TOTAL_BYTES=0
VALID_FILES=()
declare -A FILE_SIZES # Associative array to store sizes mapped to URLs

echo "Checking file sizes and server availability..."
echo

for URL in "${FILES[@]}"; do
    # Added timeouts and retries to prevent infinite hangs on bad connections
    SIZE=$(curl --retry 3 --retry-delay 2 --connect-timeout 10 --max-time 15 -sIL "$URL" \
    | awk 'tolower($1)=="content-length:" {print $2}' \
    | tail -n1 \
    | tr -d '\r')

    if [[ -z "$SIZE" || ! "$SIZE" =~ ^[0-9]+$ ]]; then
        echo "[SKIPPED] Could not determine size for: $(basename "$URL")"
        continue
    fi

    VALID_FILES+=("$URL")
    FILE_SIZES["$URL"]=$SIZE
    TOTAL_BYTES=$((TOTAL_BYTES + SIZE))

    SIZE_MB=$(awk "BEGIN {printf \"%.2f\", $SIZE/1024/1024}")
    echo "[OK] $(basename "$URL") (${SIZE_MB} MB)"
done

if [ ${#VALID_FILES[@]} -eq 0 ]; then
    echo "No downloadable files with known sizes were found. Exiting."
    exit 1
fi

# 2. Disk Space Check (Cross-platform compatible using POSIX output)
FREE_SPACE_KB=$(df -k "$DOWNLOAD_DIR" | awk 'NR==2 {print $4}')
FREE_SPACE_BYTES=$((FREE_SPACE_KB * 1024))

if [ "$TOTAL_BYTES" -gt "$FREE_SPACE_BYTES" ]; then
    echo "[FATAL] Insufficient disk space."
    echo "Required: $(awk "BEGIN {printf \"%.2f\", $TOTAL_BYTES/1024/1024}") MB"
    echo "Available: $(awk "BEGIN {printf \"%.2f\", $FREE_SPACE_BYTES/1024/1024}") MB"
    exit 1
fi

TOTAL_MB=$(awk "BEGIN {printf \"%.2f\", $TOTAL_BYTES/1024/1024}")

echo "========================================"
echo "Total files to download: ${#VALID_FILES[@]}"
echo "Total download size: ${TOTAL_MB} MB"
echo "Available disk space: $(awk "BEGIN {printf \"%.2f\", $FREE_SPACE_BYTES/1024/1024}") MB"
echo "========================================"
echo

# 3. Flexible User Prompt
read -p "Proceed with download? (y/N): " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy](es)?$ ]]; then
    echo "Download cancelled."
    exit 0
fi

echo
echo "Starting downloads..."
echo

SUCCESS_COUNT=0
FAILED_COUNT=0

for URL in "${VALID_FILES[@]}"; do
    FILE_NAME=$(basename "$URL")
    DEST_PATH="$DOWNLOAD_DIR/$FILE_NAME"
    EXPECTED_SIZE=${FILE_SIZES["$URL"]}

    # 4. Idempotency: Skip if already fully downloaded
    if [ -f "$DEST_PATH" ]; then
        LOCAL_SIZE=$(wc -c < "$DEST_PATH" | tr -d ' ')
        if [ "$LOCAL_SIZE" -eq "$EXPECTED_SIZE" ]; then
            echo "[SKIPPED] $FILE_NAME is already fully downloaded."
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
            continue
        fi
    fi

    echo "Downloading: $FILE_NAME"

    # 5. Robust Download: Resume partials (-C -), retries, timeouts
    if curl --retry 5 --retry-connrefused --retry-delay 3 --connect-timeout 15 -C - -fL --progress-bar "$URL" -o "$DEST_PATH"; then
        
        # 6. Post-download Verification
        LOCAL_SIZE=$(wc -c < "$DEST_PATH" | tr -d ' ')
        if [ "$LOCAL_SIZE" -eq "$EXPECTED_SIZE" ]; then
            echo "[SUCCESS] $FILE_NAME verified."
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        else
            echo "[ERROR] Size mismatch for $FILE_NAME. Expected $EXPECTED_SIZE, got $LOCAL_SIZE."
            rm -f "$DEST_PATH"
            FAILED_COUNT=$((FAILED_COUNT + 1))
        fi
    else
        echo "[ERROR] Failed to download: $URL"
        FAILED_COUNT=$((FAILED_COUNT + 1))
        # Note: We do NOT remove the partial file here, allowing `curl -C -` to resume it on the next run.
    fi
    echo
done

echo "========================================"
echo "Download Summary"
echo "========================================"
echo "Successful/Verified: $SUCCESS_COUNT"
echo "Failed:              $FAILED_COUNT"
echo "Saved to:            $DOWNLOAD_DIR"
echo "========================================"

if [ "$FAILED_COUNT" -gt 0 ]; then
    exit 1
fi