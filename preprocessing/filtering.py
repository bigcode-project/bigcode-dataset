import time
import argparse
from datasets import load_dataset
import numpy as np
from utils.manual_sharding import save_manual_shards


def parseArgs():
    parser = argparse.ArgumentParser(description="Filtering code datasets")
    parser.add_argument(
        "--dataset_name",
        default="bigcode/python_permissive",
        type=str,
        help="HF repo name/path of the dataset.",
    )
    parser.add_argument(
        "--subset",
        default="data/",
        type=str,
        help="Data subset to use.",
    )
    parser.add_argument(
        "--line_max",
        default=1000,
        type=int,
        help="Max line length",
    )
    parser.add_argument(
        "--line_mean",
        default=100,
        type=int,
        help="Mean line length",
    )
    parser.add_argument(
        "--alpha_frac",
        default=0.25,
        type=float,
        help="Fraction of alphanumeric characters",
    )
    parser.add_argument(
        "--num_workers",
        default=96,
        type=int,
        help="Number of workers for multiprocessing",
    )
    parser.add_argument(
        "--split",
        default="train",
        type=str,
        help="Datasset split to process",
    )
    parser.add_argument(
        "--push_to_hub",
        action="store_true",
        help="Push the dataset to the Hub",
    )
    parser.add_argument(
        "--remote_repo",
        default="stack-pjj-filtered",
        type=str,
        help="HF repo name of the target dataset in the hub.",
    )
    parser.add_argument(
        "--hub_username",
        default="loubnabnl",
        type=str,
        help="Username for the hub",
    )
    return parser.parse_args()


def filter(example):
    """Filter files that are config or test files"""
    if example["max_line_length"] > args.line_max:
        return False
    elif example["avg_line_length"] > args.line_mean:
        return False
    elif example["alphanum_fraction"] < args.alpha_frac:
        return False
    return True


def get_size_nl(example):
    size = len(example["content"])
    return {"size": size}


args = parseArgs()

# Load dataset
t_start = time.time()
print(f"Loading dataset {args.dataset_name}")
dataset = load_dataset(
    args.dataset_name, data_dir=args.subset, split=args.split, use_auth_token=True
)
print(f"Time to load dataset: {time.time()-t_start:.2f}")

dataset = dataset.map(get_size_nl)
old_size_gb = sum(dataset["size"])

# Run filtering
t_start = time.time()
old_size = len(dataset)
ds = dataset.filter(filter)
print(f"Time to filter dataset: {time.time()-t_start:.2f}")
print(f"\nSize of original dataset: {old_size}")
print(f"Size of filtered dataset: {len(ds)}")
print(
    f"\nPercentage of removed files: {np.round((old_size - len(ds))*100/old_size, 2)}%"
)

print("\nCounting size in Gb of the new datase")
new_size_gb = sum(ds["size"])

print(f"current size in Gb is {np.round(new_size_gb/10**9, 4)}")
print(f"old size in Gb is {np.round(old_size_gb/10**9, 4)}")
print(f"volume removed: {np.round((old_size_gb-new_size_gb)*100/old_size_gb, 2)}%")


if args.push_to_hub:
    print("\nPushing dataset to the Hub")
    ds.push_to_hub(args.remote_repo)
else:
    print(f"Saving the dataset in manual shards")
    save_manual_shards(ds, user=args.hub_username, remote_dataset_repo=args.remote_repo)
print("Dataset successfully saved")
