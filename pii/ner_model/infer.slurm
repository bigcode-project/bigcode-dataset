#!/bin/bash
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1          # crucial - only 1 task per dist per node!
#SBATCH --cpus-per-task=96
#SBATCH --gres=gpu:8
#SBATCH --exclusive
#SBATCH --partition=production-cluster
#SBATCH --output=/fsx/leandro/logs/bigcode/%x-%j.out

set -x -e

source /admin/home/leandro/.bashrc

conda activate trl


# Training setup
GPUS_PER_NODE=8
# so processes know who to talk to
MASTER_ADDR=$(scontrol show hostnames $SLURM_JOB_NODELIST | head -n 1)
MASTER_PORT=6000
NNODES=$SLURM_NNODES
NODE_RANK=$SLURM_PROCID 
WORLD_SIZE=$(($GPUS_PER_NODE*$NNODES))


export HF_DATASETS_CACHE="/fsx/leandro/.cache"

PATH_TO_LOG=/fsx/leandro/logs/bigcode
LOG_PATH=$PATH_TO_LOG/main_log.txt
LANGUAGE=$1 

echo "START TIME: $(date) with LANG: $LANGUAGE"


cd /fsx/leandro/git/bigcode-dataset-fork/bigcode-dataset/pii/ner_model_training

CMD=" \
    ner_inference.py \
    --model_name bigcode/bigcode-encoder-pii-ner-v2 \
    --dataset parquet \
    --subset /fsx/leandro/data/bigcode/the-stack-march/data/$LANGUAGE \
    --out_path /fsx/leandro/data/pii_result/ \
    --process_batch_size 100000 \
    "

export LAUNCHER="accelerate launch \
    --num_processes 8 \
    "

# hide duplicated errors using this hack - will be properly fixed in pt-1.12
# export TORCHELASTIC_ERROR_FILE=/tmp/torch-elastic-error.json

# force crashing on nccl issues like hanging broadcast
export NCCL_ASYNC_ERROR_HANDLING=1
# export NCCL_DEBUG=INFO
# export NCCL_DEBUG_SUBSYS=COLL
# export NCCL_SOCKET_NTHREADS=1
# export NCCL_NSOCKS_PERTHREAD=1
# export CUDA_LAUNCH_BLOCKING=1

# AWS specific
export NCCL_PROTO=simple
export RDMAV_FORK_SAFE=1
export FI_EFA_FORK_SAFE=1
export FI_EFA_USE_DEVICE_RDMA=1
export FI_PROVIDER=efa
export FI_LOG_LEVEL=1
export NCCL_IB_DISABLE=1
export NCCL_SOCKET_IFNAME=ens

export CUDA_HOME=/usr/local/cuda-11.6
export LD_PRELOAD=$CUDA_HOME/lib/libnccl.so
export LD_LIBRARY_PATH=$CUDA_HOME/efa/lib:$CUDA_HOME/lib:$CUDA_HOME/lib64:$LD_LIBRARY_PATH

SRUN_ARGS=" \
    --wait=60 \
    --kill-on-bad-exit=1 \
    "

# py-spy top -s -i -n -- $LAUNCHER --node_rank $SLURM_PROCID --role $SLURMD_NODENAME: $CMD
clear; srun $SRUN_ARGS --jobid $SLURM_JOB_ID bash -c "$LAUNCHER --role \$SLURMD_NODENAME: $CMD" 2>&1 | tee $LOG_PATH

echo "END TIME: $(date)"