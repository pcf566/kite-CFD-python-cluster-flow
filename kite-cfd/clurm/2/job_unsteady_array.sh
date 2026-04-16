#!/bin/bash
#SBATCH -J fluent_unsteady
#SBATCH -p cnall
#SBATCH -N 4
#SBATCH --ntasks-per-node=56
#SBATCH --array=1-17
#SBATCH -o slurm.%A_%a.out
#SBATCH -e slurm.%A_%a.err
#SBATCH --no-requeue

set -euo pipefail

cd ~/WORK/psf/fluent_work1_1

module load soft/anaconda3/config

echo "============================================================"
echo "SLURM_JOB_ID         = ${SLURM_JOB_ID:-}"
echo "SLURM_ARRAY_TASK_ID  = ${SLURM_ARRAY_TASK_ID:-}"
echo "SLURM_JOB_NODELIST   = ${SLURM_JOB_NODELIST:-}"
echo "工作目录              = $(pwd)"
echo "开始时间              = $(date)"
echo "============================================================"

python main_unsteady.py --processors 224