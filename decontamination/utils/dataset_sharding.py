import time
from multiprocessing import Pool
from tqdm import tqdm


def save_shard(shard_tuple):
        """Save shard"""
        filename, shard = shard_tuple
        # use to_json instead to save as json file
        shard.to_parquet(filename)


def shard_dataset(ds, shard_size, output_dir, num_proc):
    if ds._indices is not None:
        dataset_nbytes = ds.data.nbytes * len(ds._indices) / len(ds.data)
    else:
        dataset_nbytes = ds.data.nbytes
    num_shards = int(dataset_nbytes / shard_size) + 1
    print(f"Number of shards: {num_shards}")

    print("sharding the dataset")
    t_start = time.time()
    shards = (ds.shard(num_shards=num_shards, index=i, contiguous=True) for i in range(num_shards))
    # use f"{OUT_PATH}/data/train-{index:05d}-of-{num_shards:05d}.json" instead for json files
    filenames = (f"{output_dir}/train-{index:05d}-of-{num_shards:05d}.parquet" for index in range(num_shards))

    with Pool(num_proc) as p:
        list(tqdm(p.imap_unordered(save_shard, zip(filenames, shards), chunksize=4), total=num_shards))
    print(f"Time to save dataset: {time.time()-t_start:.2f}")
