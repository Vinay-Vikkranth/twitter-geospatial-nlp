#!/bin/bash
#SBATCH --job-name=project53-label
#SBATCH --cpus-per-task=2
#SBATCH --mem=24G
#SBATCH --gres=gpu:1
#SBATCH --time=24:00:00
#SBATCH --output=label-%j.log
# Add Harvard's confirmed GPU account/partition before submitting.
set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit from the project folder}"
# Set HF_TOKEN privately, or use hf auth login. Never put it in this file.
python run.py label --mode pilot --max-tweets 100
# After manually validating a representative pilot, run:
# python run.py label --mode production
