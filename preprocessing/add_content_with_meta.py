"""
Create a dataset with a single `content_with_meta` field
"""

import logging
import time
from functools import partial

import numpy as np
from datasets import load_dataset
from datasets.utils.logging import set_verbosity_info
from transformers import AutoTokenizer, HfArgumentParser

from arguments import ContentWithMetaArguments
from utils.manual_sharding import save_manual_shards


REPONAME_TOKEN = "<reponame>"
FILENAME_TOKEN = "<filename>"
STARS_TOKEN = "<gh_stars>"


def parse_args():
    parser = HfArgumentParser(ContentWithMetaArguments)
    return parser.parse_args()


def get_num_stars_bucket(num_stars: int) -> str:
    if num_stars is None or num_stars == 0:
        return "0"
    elif num_stars <= 10:
        return "1-10"
    elif num_stars <= 100:
        return "10-100"
    elif num_stars <= 1000:
        return "100-1000"
    else:
        return "1000+"
    

def content_with_meta(example):
    # TODO
    res = ""
    # repo-name
    if np.random.binomial(n=1, p=args.add_repo_name_prob):
        res += f"{REPONAME_TOKEN}{example['max_stars_repo_name']}"
    # file-name
    if np.random.binomial(n=1, p=args.add_file_name_prob):
        res += f"{FILENAME_TOKEN}{example['max_stars_repo_path']}"
    # number of stars
    if np.random.binomial(n=1, p=args.add_num_stars_prob):
        num_stars = get_num_stars_bucket(example['max_stars_count'])
        res += f"{STARS_TOKEN}{num_stars}"
    if len(res) > 0:
        res += "\n"
    res += example['content']
    
    return {"content_with_meta": res}


if __name__ == "__main__":
    args = parse_args()

    set_verbosity_info()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO,
        handlers=[logging.FileHandler(args.log_file), logging.StreamHandler()],
    )
    logger.info(
        f"** The job is running with the following arguments: **\n{args}\n **** "
    )
    # Load dataset
    t_start = time.time()
    logger.info(f" ===== Loading {args.dataset_name} and subset {args.subset}=====")
    dataset = load_dataset(
        args.dataset_name, split=args.split, data_dir=args.subset, use_auth_token=True, num_proc=args.num_workers
    )
    logger.info(f"Dataset loaded in {time.time() - t_start:.2f} seconds")
    logger.info(f"Dataset: {dataset}")

    logger.info(
        f"Dataset size: {len(dataset)} examples, {sum(dataset['size']) / 1e9:.2f} GB"
    )
    logger.info(f"Adding content_with_meta field: ")

    dataset = dataset.map(
        content_with_meta,
        remove_columns=["content"],
        num_proc=16
    )

    logger.info(f"Dataset processed in {time.time() - t_start:.2f} seconds")


    # Save dataset
    logger.info(
        f"Final dataset has {len(dataset)} samples and {sum(dataset['size']) / 1e9:.2f} GB of code"
    )
    logger.info("===== Saving final dataset =====")

    t_start = time.time()
    if args.push_to_hub:
        logger.info(f"Pushing dataset to the Hub at {args.remote_repo}")
        dataset.push_to_hub(args.remote_repo)
    else:
        print(
            f"Saving the dataset in manual shards in a clone of {args.hub_username + args.remote_repo}"
        )
    
    save_manual_shards(
        dataset, user=args.hub_username, remote_dataset_repo=args.remote_repo, out_path=args.out_path,  subset=args.subset
    )
    logger.info(f"Dataset successfully saved at {args.out_path}/{args.subset} in {time.time() - t_start:.2f} seconds")
