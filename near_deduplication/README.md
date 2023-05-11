# Near deduplication

This is our implementation of near deduplication for BigCode dataset. It is largely evolved from the [original repo](https://github.com/bigcode-project/bigcode-analysis/tree/main/data_analysis/near-deduplication).

### Setup

````
pip install -r requirements.txt
````

Login to be able to be able to push the dataset to the hub after deduplication and clone your huggingface-hub repositories:

````
huggingface-cli login
````

And make sure you have git-lfs installed.

### Usage

```bash
# For details on the arguments, see the help message
python minhash_deduplication.py --help
# Quick example
python minhash_deduplication.py --dataset codeparrot/codeparrot-clean-valid \
    --split train \
    --column content \
    --cache-dir .cache \
    --min-ngram-size 5
# For details on the arguments, see the help message
python minhash_deduplication.py --help
```

Spark Script

```bash
# Upload the dataset to a bigquery table first!
export CLUSTER_NAME=chenghao-temp
export PROJECT_ID=huggingface-science-codeparrot
export REGION=us-central1
export ZONE=us-central1-a

gcloud dataproc clusters create $CLUSTER_NAME \
    --enable-component-gateway \
    --region $REGION \
    --zone $ZONE \
    --master-machine-type c2d-standard-16 \
    --master-boot-disk-size 500 \
    --num-workers 10 \
    --worker-machine-type c2d-standard-16 \
    --worker-boot-disk-size 500 \
    --image-version 2.0-debian10 \
    --project $PROJECT_ID

gcloud dataproc jobs submit pyspark --cluster ${CLUSTER_NAME} \
    --region $REGION \
    --jars gs://spark-lib/bigquery/spark-bigquery-latest_2.12.jar \
    --driver-log-levels root=WARN \
    --properties="spark.executor.memory"="50g","spark.driver.memory"="8g","spark.executor.cores"="14" \
    near_deduplication/minhash_deduplication_spark.py \
    -- \
    --table "huggingface-science-codeparrot.the_stack_java.java" \
    --output "gs://chenghao-data/dataproc_output/deduplicated" \
    --min_ngram_size 5 \
    --ngram_size 5 \
    --threshold 0.7
```

With above settings, it took about 40 minutes to deduplicate the Java subset (42 million docs, 319GB), 15x faster than the following python implementation in a comparable single-machine environment. In terms of scaling, it took about 5 hours to deduplicate the 1.3 TB json subset of the Stack with a 15-machine cluster. 

Warning: Big Query might change your list schema in the output! You can use the following code to restore the format (credit to [@RaymondLi0](https://github.com/RaymondLi0)):

```python
LIST_COLUMNS = ['max_stars_repo_licenses', 'max_issues_repo_licenses', 'max_forks_repo_licenses']
def fix_license_cols(example):
    for col in LIST_COLUMNS:
        example[col] = [x["item"] for x in example[col]["list"]]
    return example
...
ds = ds.map(fix_license_cols)
```

#### Python Implementation Analysis

This section is a brief analysis of the time complexity and memory complexity. It is not a rigorous proof, but it should give you a general idea of how the implementation works.

##### Scaling

To understand the limitation of current deduplication implementation, it is important to have an idea of how each step in the pipeline affects the overall time:
1. Hashing is fast, but it takes longer for long documents. Hashing scales with both the number of cores and single core performance (clock speed, for example). With `datasets`'s caching, it also does not require much memory.
2. Indexing is basically putting hash signatures into different buckets. This is one bottleneck in this pipeline. In an ideal situation where MapReduce is seamlessly integrated with other parts, it can be further improved with distributed buckets. Finding duplicates can be done after the indexing step or during the index building.
4. Depending on how you decide to group duplicates, you can build a graph and then do connected component analysis or use simple algorithm like union-find.
5. What to do with a group of duplicates is also an open question. We opt to keep one document within a group/cluster in this case.

##### Experiments

We report here some stats on the experiments we did along the way with a 80-core machine on GCP (M1):

For SantaCoder, our results can be replicated by the following commands using [older version of the code](https://github.com/bigcode-project/bigcode-analysis/tree/fdd70bffb9cceab031f6d682edf83b5af49e8aaf):

```bash
python minhash_deduplication.py --dataset bigcode/the-stack-dedup-pjj --data-dir data/java --revision v1.1.a1 --cache-dir cache2 --ngram-size 5 --threshold 0.7 --min-token-length 10 --fast
python minhash_deduplication.py --dataset bigcode/the-stack-dedup-pjj --data-dir data/javascript --revision v1.1.a1 --cache-dir cache2 --ngram-size 5 --threshold 0.7 --min-token-length 10 --fast
python minhash_deduplication.py --dataset bigcode/the-stack-dedup-pjj --data-dir data/python --revision v1.1.a1 --cache-dir cache2 --ngram-size 5 --threshold 0.7 --min-token-length 10 --fast
```

Java Results as of Dec 20, 2022
```
load_dataset                    : 3414.68 seconds
minhash                         : 22966.13 seconds
clustering                      : 7676.72 seconds
filtering                       : 1118.62 seconds
save                            : 3105.66 seconds
Data Number (before)            : 40113161
Data Number (after)             : 21108567 (52.62%)
Duplicate Number                : 19004594 (47.38%)
Total Time                      : 38281.88 seconds (10.6 hours)
```


Java (already deduplicated) Results as of Dec 2, 2022
```
Load Dataset                    : 77.18 seconds                                                                                       
Embed                           : 5052.87 seconds                                                                                     
Create Index                    : 16253.12 seconds                                                                                    
Save Index                      : 0.00 seconds                                                                                        
Freeze Memory                   : 0.00 seconds                                                                                        
Query                           : 1321.61 seconds                                                                                     
Save Neighbors                  : 0.00 seconds                                                                                        
Unfreeze Memory                 : 0.00 seconds                                                                                        
Clustering                      : 10825.30 seconds                                                                                    
Total Processing Time           : 34919.87 seconds                                                                                    
Deduplicate                     : 605.83 seconds                                                                                      
Save Deduplicated               : 2356.10 seconds                                                                                     
Language                        : java                                                                                                
Data Number (before filtering)  : 25124914                                                                                            
Data Number (after filtering)   : 24972491                                                                                            
Duplicate Number                : 4822205 (19.31%)                                                                                    
Total Reduction                 : 4974628 (19.80%)                                                                                    
Total Time                      : 37881.83 seconds (10.5 hours)                                                                        
```

More details can be found on https://zippy-anise-556.notion.site/Deduplication-Log-d75d1b3f2e684e96a12b069c5aff68cb. We ignore physical size change because it is less relevant to the deduplication process and varies a lot depending on the data format.