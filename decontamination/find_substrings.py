from glob import glob
import json
import os
import sys
import argparse

from datasets import load_dataset

from benchmark_data import filter_file
from utils.dataset_sharding import shard_dataset
from utils.utils import add_dict


SHARD_SIZE = 1000 << 20  # 1GB
LANGUAGE_COL = "lang"


def aggregate_meta(tmp_meta_dir: str):
    res = {}
    for file in glob(f"{tmp_meta_dir}/*-meta.json"):
        with open(file, "r") as f:
            meta = json.load(f)
        add_dict(res, meta)
    return res


def concatenate_meta(tmp_meta_dir: str):
    res = []
    for file in glob(f"{tmp_meta_dir}/*-excluded-data.json"):
        with open(file, "r") as f:
            meta = json.load(f)
        res += meta
    return res


class Meta:
    def __init__(self) -> None:
        self.meta_dict = dict()
    
    def update(self, lang: str, filter_reason: str):
        if lang not in self.meta_dict:
            self.meta_dict[lang] = {}
        if filter_reason not in self.meta_dict[lang]:
            self.meta_dict[lang][filter_reason] = 0
        self.meta_dict[lang][filter_reason] += 1


def filter_substrings(batch: dict, idx, tmp_meta_dir: str):
    meta = Meta()
    excluded_data = []
    features = batch.keys()
    res = {k: [] for k in features}
    for sample in zip(*[batch[k] for k in features]):
        sample = {k: v for k, v in zip(features, sample)}
        should_include, filter_reason, matched_substring = filter_file(sample, return_matched=True)
        if not should_include:
            meta.update(sample[LANGUAGE_COL], filter_reason)
            excluded_data.append({
                "data": sample,
                "filter_reason": filter_reason,
                "matched_substring": matched_substring
            })
        else:
            # Add to output
            for k in features:
                res[k].append(sample[k])

    # Record Meta
    with open(os.path.join(tmp_meta_dir, f"{idx[0]}-{idx[-1]}-meta.json"), "w") as f:
        json.dump(meta.meta_dict, f)
    with open(os.path.join(tmp_meta_dir, f"{idx[0]}-{idx[-1]}-excluded-data.json"), "w") as f:
        json.dump(excluded_data, f, indent=4)
    return res


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset-name",
        default="bigcode/the-stack-pjjs-no-pii-filtered",
        type=str,
        help="Name or path of the HF dataset to decontaminate"
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=str,
        help="Path to save output data and metadata"
    )
    parser.add_argument(
        "--num-proc",
        type=int,
        default=200,
        help="Number of processes"
    )
    return parser.parse_args()


def main():
    args = arguments()
    # dataset_name = "bigcode/the-stack-pjjs-no-pii-filtered"
    output_dir = args.output_dir
    tmp_meta_dir = f"{output_dir}/tmp/meta"
    data_dir = f"{output_dir}/data"

    ds = load_dataset(
        args.dataset_name, split="train", use_auth_token=True,
        # chunksize=40 << 20
    )

    os.makedirs(tmp_meta_dir)
    os.makedirs(data_dir)

    filtered = ds.map(
        filter_substrings,
        batched=True,
        with_indices=True,
        num_proc=args.num_proc,
        fn_kwargs={
            "tmp_meta_dir": tmp_meta_dir,
        },
        load_from_cache_file=False,
    )
    print("Number of samples in the new dataset: ", len(filtered))

    # Dump meta
    meta = aggregate_meta(tmp_meta_dir)
    print(meta)
    with open(os.path.join(output_dir, "meta.json"), "w") as f:
        json.dump(meta, f)
    # Dump excluded-data.json
    meta = concatenate_meta(tmp_meta_dir)
    print("Number of excluded examples: ", len(meta))
    with open(os.path.join(output_dir, "excluded-data.json"), "w") as f:
        json.dump(meta, f)

    # Save shards
    shard_dataset(filtered, SHARD_SIZE, data_dir, num_proc=args.num_proc)


if __name__ == "__main__":
    main()
