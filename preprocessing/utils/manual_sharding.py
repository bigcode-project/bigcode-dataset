import os
import time
from multiprocessing import Pool
from tqdm import tqdm

from huggingface_hub import Repository


def save_shard(shard_tuple):
    """Save shard"""
    filename, shard = shard_tuple
    # use to_json instead to save as json file
    shard.to_parquet(filename)


def save_manual_shards(ds, user="loubnabnl", remote_dataset_repo="bigcode-pii-pjj", out_path=None, subset="data/"):
    """Save sharded data
    Args:
        ds (Dataset): dataset to be saved
        user (str): user name
        remote_dataset_repo (str): remote dataset repository
        out_path (str): path to save the shards
        subset (str): path inside the local repo to save the shards
    """
    # this will create a folder OUT_PATH that is a clone of REMOTE_DATASET_REPO
    # you can save the shards inside it and do git add/commit/push to push data to the hub
    out_path = remote_dataset_repo if out_path is None else out_path
    # if out path doesnt already exist
    if not os.path.exists(out_path):
        repo = Repository(
            local_dir=out_path,
            clone_from=user + "/" + remote_dataset_repo,
            repo_type="dataset",
            private=True,
            use_auth_token=True,
            git_user=user,
        )

    # files will be numerous we save them in a folder called `subset` inside out_path
    os.makedirs(f"{out_path}/{subset}")
    SHARD_SIZE = 1000 << 20
    if ds._indices is not None:
        dataset_nbytes = ds.data.nbytes * len(ds._indices) / len(ds.data)
    else:
        dataset_nbytes = ds.data.nbytes
    num_shards = int(dataset_nbytes / SHARD_SIZE) + 1
    print(f"Number of shards: {num_shards}")

    print("sharding the dataset")
    t_start = time.time()
    shards = (
        ds.shard(num_shards=num_shards, index=i, contiguous=True)
        for i in range(num_shards)
    )
    # use f"{OUT_PATH}/data/train-{index:05d}-of-{num_shards:05d}.json" instead for json files
    filenames = (
        f"{out_path}/{subset}/train-{index:05d}-of-{num_shards:05d}.parquet"
        for index in range(num_shards)
    )

    with Pool(16) as p:
        list(
            tqdm(
                p.imap_unordered(save_shard, zip(filenames, shards), chunksize=4),
                total=num_shards,
            )
        )
    print(f"Time to save dataset: {time.time()-t_start:.2f}")
    # to push dataset to hub do: git add/commit/push inside OUT_PATH
