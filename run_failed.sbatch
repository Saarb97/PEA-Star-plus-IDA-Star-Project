#!/bin/bash
#SBATCH --partition=main
#SBATCH --time=9:00:00
#SBATCH --job-name=pea_ida_retry
#SBATCH --output=logs/retry_%A_%a.out
#SBATCH --error=logs/retry_%A_%a.err
#SBATCH --mail-user=saarbu@post.bgu.ac.il
#SBATCH --mail-type=FAIL
#SBATCH --mem=8G
#SBATCH --cpus-per-task=1

mkdir -p logs

module load anaconda
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate build_env

# Extract command for this task ID (1-indexed)
CMD=$(sed -n "${SLURM_ARRAY_TASK_ID}p" failed_jobs.txt)

if [ -z "$CMD" ]; then
    echo "Error: No command found at line ${SLURM_ARRAY_TASK_ID} in failed_jobs.txt"
    exit 1
fi

echo "Task ID: ${SLURM_ARRAY_TASK_ID}"
echo "Running command: ${CMD}"
echo "----------------------------------------"

eval "$CMD"
