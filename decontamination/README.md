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

### Using a cached decontamination run

The results from a previous decontamination run can be used to speed-up the script under the following conditions:
- the new dataset is a subset (or equal) of the previously decontaminated dataset
- the new set of strings to decontaminate contains the strings from the previous run. (Code does not yet support the case where some strings are no longer decontaminated)

```bash
python find_substrings.py --dataset-name bigcode/stack-dedup-alt-filter-no-pii --output-dir /path/to/output  --num-proc 32 --cached-decontamination-dir /path/to/previous/output/ --cache-retrieval-key content --split-languages
```
