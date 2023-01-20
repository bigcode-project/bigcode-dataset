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

## Near Matching with MinHash and LSH

This is similar to the near deduplication script `data_analysis/near-deduplication/minhash_deduplication_alt.py` with one modification: we use benchmark datasets as index source instead of the dataset itself.

### Usage:
1. Update the script to include any benchmark you want to check against in `DATASETS_TO_CHECK`. Be sure to create a global variable for the index using the same name in that config. Benchmark columns should be of type string or sequence of string, so that they can be concatenated.
2. Then you can run the script by
```bash
pip install -r requirements_minhash.txt
# Quick example
python minhash.py \
  --dataset codeparrot/codeparrot-clean-valid \
  --split train \
  --column content \
  --cache-dir .cache \
  --verbose
# Check parameters with the help message
python minhash.py --help
```