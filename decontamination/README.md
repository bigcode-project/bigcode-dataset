# Decontamination

This directory contains a script to decontaminate data with:

1. Exact substring matching `find_substrings.py`
2. Near-matching with MinHash: for next iterations? See https://github.com/bigcode-project/bigcode-analysis/tree/main/data_analysis/decontamination

## Exact substring matching

This script was used to produce this [dataset](https://huggingface.co/datasets/bigcode/the-stack-pjjs-decontaminate).
```bash
pip install -r requirements.txt
python find_substrings.py --dataset-name bigcode/the-stack-subset-py-js-java-450k --output-dir /path/to/output --num-proc 32
```

