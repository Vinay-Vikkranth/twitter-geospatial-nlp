#!/bin/bash
#SBATCH --job-name=project53-extract
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=24:00:00
#SBATCH --output=extract-%j.log
# Add Harvard's confirmed account/partition options before submitting.
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from the project folder}"
: "${GV_RAW_TWEETS_DIR:?Set the archive path}"
: "${NAIVE_TIMESTAMP_TZ:?Confirm archive timezone, e.g. UTC}"
python run.py doctor
python run.py filter --mode pilot --archive "$GV_RAW_TWEETS_DIR" --naive-timezone "$NAIVE_TIMESTAMP_TZ" --max-files 5
# After reviewing pilot logs/coverage/runtime, run production separately with:
# python run.py filter --mode production --archive "$GV_RAW_TWEETS_DIR" --naive-timezone "$NAIVE_TIMESTAMP_TZ" --coverage /path/to/verified_coverage.csv
