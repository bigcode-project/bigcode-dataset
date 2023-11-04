# Near deduplication

This is our implementation of near deduplication for BigCode dataset. It is largely evolved from the [original repo](https://github.com/bigcode-project/bigcode-analysis/tree/main/data_analysis/near-deduplication).

### Setup

````
pip3 install -r requirements.txt
````

### Usage

```bash
# For details on the arguments, see the help message
python3 minhash_deduplication.py --help

# Quick example
python3 convert_raw_code_to_pickle.py \
    --input_dir UnrealEngine \
    --output_dir output \
    --ext None

python3 minhash_deduplication.py \
    --input-dir output/converted \
    --column content \
    --ngram-size 5 \
    --num-perm 256 \
    --threshold 0.7 \
    --output output

python3 restore_to_raw_code.py \
    --input_path "output/deduplicated/ngram_5_num_perm_256_threshold_0.7/UnrealEngine" \
    --output_path "output/restored/ngram_5_num_perm_256_threshold_0.7"
```

#### Python Implementation Analysis

This section is a brief analysis of the time complexity and memory complexity. It is not a rigorous proof, but it should give you a general idea of how the implementation works.

##### Scaling

To understand the limitation of current deduplication implementation, it is important to have an idea of how each step in the pipeline affects the overall time:
1. Hashing is fast, but it takes longer for long documents. Hashing scales with both the number of cores and single core performance (clock speed, for example). With `datasets`'s caching, it also does not require much memory.
2. Indexing is basically putting hash signatures into different buckets. This is one bottleneck in this pipeline. In an ideal situation where MapReduce is seamlessly integrated with other parts, it can be further improved with distributed buckets. Finding duplicates can be done after the indexing step or during the index building.
4. Depending on how you decide to group duplicates, you can build a graph and then do connected component analysis or use simple algorithm like union-find.
5. What to do with a group of duplicates is also an open question. We opt to keep one document within a group/cluster in this case.

