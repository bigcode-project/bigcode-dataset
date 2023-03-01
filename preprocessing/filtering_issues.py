"""Filtering GitHub issues dataset"""

import logging
import time
from functools import partial

from datasets import load_dataset
from datasets.utils.logging import set_verbosity_info
from transformers import HfArgumentParser

from arguments import FilteringArguments
from utils.manual_sharding import save_manual_shards
from utils.utils_issues import (
    filter_based_users,
    merge_text_columns,
    remove_bot_comments,
    replace_usernames,
    strip_automated_email_text,
    truncate_long_comments,
)

MIN_CHARS = 200
MAX_CHARS = 7000
MAX_EVENTS = 10
MAX_LINES = 80


def parse_args():
    parser = HfArgumentParser(FilteringArguments)
    return parser.parse_args()


def log_stats(logger, filter_name, old_size, new_size, old_size_gb, new_size_gb):
    logger.info(
        f"Dataset size before {filter_name}: {old_size} issues, total text in events is {old_size_gb/ 1e9:.2f} GB"
    )
    logger.info(
        f"Dataset size after {filter_name}: {new_size} issues, total text in events is {new_size_gb/ 1e9:.2f} GB"
    )
    logger.info(
        f"Percentage filtered issues {100 * (old_size - new_size) / old_size:.2f}%"
    )
    logger.info(
        f"Percentage filtered volume of text {100 * (old_size_gb - new_size_gb) / old_size_gb:.2f}%"
    )


def preprocess(logger, args):
    # Load dataset
    t_start = time.time()
    logger.info(f" ===== Loading {args.dataset_name} and subset {args.subset}=====")
    dataset = load_dataset(
        args.dataset_name,
        split=args.split,
        data_dir=args.subset,
        use_auth_token=True,
        num_proc=args.num_workers,
    )
    logger.info(f"Dataset {dataset}\nLoaded in {time.time() - t_start:.2f} seconds")

    # basic processing
    logger.info(f"===== Basic processing dataset=====")
    dataset = (
        dataset.map(merge_text_columns, num_proc=args.num_workers)
        .map(strip_automated_email_text, num_proc=args.num_workers)
        .map(
            lambda x: {"text_size": sum([len(event["text"]) for event in x["events"]])},
            num_proc=args.num_workers,
        )
    )
    old_size = len(dataset)
    old_size_gb = sum(dataset["text_size"])
    logger.info(
        f"Dataset size before any filtering: {old_size} issues, total text in events is {old_size_gb/ 1e9:.2f} GB"
    )

    # truncate long comments
    logger.info(f"===== Truncating long comments =====")
    dataset = dataset.map(
        partial(truncate_long_comments, max_lines=MAX_LINES), num_proc=args.num_workers
    ).map(
        lambda x: {"text_size": sum([len(event["text"]) for event in x["events"]])},
    )
    new_size_gb = sum(dataset["text_size"])
    log_stats(
        logger, "truncating long comments", old_size, old_size, old_size_gb, new_size_gb
    )

    # bot filter
    logger.info(f"===== Filtering comments from bots =====")
    dataset = dataset.map(remove_bot_comments, num_proc=args.num_workers)
    dataset = dataset.filter(lambda x: not x["bot_issue"])
    dataset = dataset.map(
        lambda x: {"text_size": sum([len(event["text"]) for event in x["events"]])},
        num_proc=args.num_workers,
    )
    new_size = len(dataset)
    new_size_gb = sum(dataset["text_size"])
    log_stats(logger, "bots filter", old_size, new_size, old_size_gb, new_size_gb)

    logger.info(f"===== Adding users and events count columns =====")
    dataset = dataset.map(
        lambda x: {"user_count": len(set(event["author"] for event in x["events"]))},
        num_proc=args.num_workers,
    ).map(lambda x: {"event_count": len(x["events"])}, num_proc=args.num_workers)

    logger.info(f"===== Filtering issues based on users and minimal size=====")
    dataset = dataset.filter(
        partial(
            filter_based_users,
            minimum=MIN_CHARS,
            maximum=MAX_CHARS,
            max_events=MAX_EVENTS,
        )
    )
    size_users = len(dataset)
    size_users_gb = sum(dataset["text_size"])
    log_stats(
        logger, "users filter", size_no_bots, size_users, size_no_bots_gb, size_users_gb
    )

    # replace usernames
    logger.info(f"===== Replacing usernames =====")
    dataset = dataset.map(replace_usernames, num_proc=args.num_workers)
    modified_data = dataset.filter(lambda x: x["modified_usernames"])
    logger.info(
        f"Percentage of issues with modified usernames: {(len(modified_data) * 100) / len(dataset):.2f}%"
    )
    logger.info(
        f"Final dataset has {size_users} samples and {size_users_gb / 1e9:.2f} GB of code"
    )
    logger.info(f"Dataset processed in {time.time() - t_start:.2f} seconds")
    return dataset


if __name__ == "__main__":
    args = parse_args()

    set_verbosity_info()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO,
        handlers=[logging.FileHandler("filtering.log"), logging.StreamHandler()],
    )
    logger.info(f"Filtering GitHub issues dataset, arguments: **\n{args}")

    dataset = preprocess(logger, args)

    # Save dataset
    t_start = time.time()
    if args.push_to_hub:
        logger.info(f"Pushing dataset to the Hub at {args.remote_repo}")
        dataset.push_to_hub(args.remote_repo)
    else:
        print(
            f"Saving the dataset in manual shards in a clone of {args.hub_username + args.remote_repo}"
        )
    save_manual_shards(
        dataset, user=args.hub_username, remote_dataset_repo=args.remote_repo
    )
    logger.info(f"Dataset successfully saved in {time.time() - t_start:.2f} seconds")
