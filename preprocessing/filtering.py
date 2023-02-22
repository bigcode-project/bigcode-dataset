"""Filter code datasets using:  
    * basic filters (line length and alphanumeric characters)
    * comments to code ratio (maximum + minimum)
    * minimum number of stars
    * tokenizer fertility ratio (char to token ratio)"""

import fnmatch
import logging
import time
from functools import partial

import numpy as np
from datasets import load_dataset
from datasets.utils.logging import set_verbosity_info
from transformers import AutoTokenizer, HfArgumentParser

from arguments import FilteringArguments
from utils.manual_sharding import save_manual_shards
from utils.text_extraction import get_nl_ratio

# define list of filters to apply
ALL_FILTERS = ["basic", "stars", "comments", "fertility"]
THRESHOLDS_FERTILITY = {"python": 2.5, "java": 2.9, "javascript": 2.6}


class MultiChoice:
    def __init__(self, choices):
        self.choices = choices

    def __contains__(self, values):
        for value in values.split(","):
            if len(fnmatch.filter(self.choices, value)) == 0:
                return False
        return True

    def __iter__(self):
        for choice in self.choices:
            yield choice


def pattern_match(patterns, source_list):
    """Returns a list containing all values of the source_list that
    match at least one of the patterns"""
    task_names = set()
    for pattern in patterns:
        for matching in fnmatch.filter(source_list, pattern):
            task_names.add(matching)
    return list(task_names)


def parse_args():
    parser = HfArgumentParser(FilteringArguments)
    parser.add_argument(
        "--filters",
        default=None,
        choices=MultiChoice(ALL_FILTERS),
        help=f"Filter from {ALL_FILTERS}, where basic stands for line length and alphanumeric charceters filters",
    )
    return parser.parse_args()


def get_comments_ratio(examples):
    """Get ratio of comments to code in each example. Requires a language argument"""
    ratio_list = []
    for code, language in zip(examples["content"], examples["lang"]):
        ratio_list.append(get_nl_ratio(code, language.lower()))
    return {"nl_ratio": ratio_list}


def convert_none_stars(examples, stars_column="max_stars_count"):
    """Converts None values in stars column to 0"""
    stars = []
    for value in examples[stars_column]:
        if value is None:
            stars.append(0)
        else:
            stars.append(value)
    return {"stars": stars}


def basic_filters(example):
    """Filter files based on line length and % alphanumeric characters"""
    if example["max_line_length"] > args.line_max:
        return False
    elif example["avg_line_length"] > args.line_mean:
        return False
    elif example["alphanum_fraction"] < args.alpha_frac:
        return False
    return True


def char_token_ratio(examples, tokenizer):
    ratio_list = []
    for code in examples["content"]:
        input_ids = tokenizer(code, truncation=False)["input_ids"]
        ratio = len(code) / len(input_ids)
        ratio_list.append(ratio)
    return {"fertility_ratio": ratio_list}


def filter_tokenizer(examples):
    """Filter files based on char to token ratio"""
    values = []
    for ratio, lang in zip(examples["fertility_ratio"], examples["lang"]):
        if ratio < THRESHOLDS_FERTILITY[lang.lower()]:
            values.append(False)
        else:
            values.append(True)
    return values


def get_size_text(example):
    return {"size": len(example["content"])}


if __name__ == "__main__":
    args = parse_args()
    print(f"Selected filters: {args.filters}")
    if args.filters is None:
        filters = ALL_FILTERS
    else:
        filters = pattern_match(args.filters.split(","), ALL_FILTERS)

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
    logger.info(f" ===== Selected filters: {filters}=====")
    # Load dataset
    t_start = time.time()
    logger.info(f" ===== Loading {args.dataset_name} and subset {args.subset}=====")
    dataset = load_dataset(
        args.dataset_name, split=args.split, data_dir=args.subset, use_auth_token=True, num_proc=args.num_workers
    )
    logger.info(f"Dataset loaded in {time.time() - t_start:.2f} seconds")
    logger.info(f"Dataset: {dataset}")
    if "size" not in dataset.column_names:
        logger.info("Add text size column")
        dataset = dataset.map(get_size_text)
    logger.info(
        f"Dataset size before any filtering: {len(dataset)} examples, {sum(dataset['size']) / 1e9:.2f} GB"
    )

    # Run pre-processing if needed
    if "stars" in filters:
        logger.info(f"===== Processing dataset to add proper stars column=====")
        dataset = dataset.map(
            convert_none_stars,
            batched=True,
            batch_size=args.batch_size,
            num_proc=args.num_workers,
        )
    if "comments" in filters:
        logger.info(
            f"===== Processing dataset to add comment to code ratio column====="
        )
        dataset = dataset.map(
            get_comments_ratio,
            batched=True,
            batch_size=args.batch_size,
            num_proc=args.num_workers,
        )
    if "fertility" in filters:
        logger.info(
            f"===== Processing dataset to add tokenizer fertility ratio column====="
        )
        tokenizer = AutoTokenizer.from_pretrained(
            args.tokenizer_name, use_auth_token=True
        )
        dataset = dataset.map(
            partial(char_token_ratio, tokenizer=tokenizer),
            batched=True,
            batch_size=args.batch_size,
            num_proc=args.num_workers,
        )
    logger.info(f"Dataset processed in {time.time() - t_start:.2f} seconds")

    # Run filtering
    for filter in filters:
        if filter == "basic":
            logger.info(
                f"===== Basic filtering with line_max {args.line_max} and avg_line {args.line_mean} and alpha_frac {args.alpha_frac}====="
            )
            old_size = len(dataset)
            old_size_gb = sum(dataset["size"])
            t_start = time.time()
            ds = dataset.filter(basic_filters)
            logger.info(f"Filtering done in {time.time() - t_start:.2f} seconds")
            logger.info(
                f"Percentage of removed files: {np.round((old_size - len(ds))*100/old_size, 2)}%"
            )
            new_size_gb = sum(ds["size"])
            logger.info(
                f"Dataset size before {filter} filtering: {old_size} examples, {old_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"Dataset size after {filter} filtering: {len(ds)} examples, {new_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"Percentage of volume removed {np.round((old_size_gb - new_size_gb)*100/old_size_gb, 2)}%"
            )
            dataset = ds

        elif filter == "stars":
            logger.info(
                f"===== Filtering based on stars with threshold {args.threshold_stars}====="
            )
            old_size = len(dataset)
            old_size_gb = sum(dataset["size"])
            t_start = time.time()
            ds = dataset.filter(lambda example: example["stars"] > args.threshold_stars)
            logger.info(f"Filtering done in {time.time() - t_start:.2f} seconds")
            logger.info(
                f"Percentage of removed files: {np.round((old_size - len(ds))*100/old_size, 2)}%"
            )
            new_size_gb = sum(ds["size"])
            logger.info(
                f"Dataset size before {filter} filtering: {old_size} examples, {old_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"Dataset size after {filter} filtering: {len(ds)} examples, {new_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"Percentage of volume removed {np.round((old_size_gb - new_size_gb)*100/old_size_gb, 2)}%"
            )
            dataset = ds

        elif filter == "comments":
            logger.info(
                f"===== Filtering on comments ratio with thresholds min: {args.min_threshold_comments}, max: {args.max_threshold_comments}====="
            )
            old_size = len(dataset)
            old_size_gb = sum(dataset["size"])
            t_start = time.time()
            ds = dataset.filter(
                lambda example: example["nl_ratio"] > args.min_threshold_comments
                and example["nl_ratio"] < args.max_threshold_comments
            )
            print(
                f"Percentiles of comments ratio 20th, 22nd, 25th, 80th, 95th and 99th: {np.percentile(dataset['nl_ratio'], [20,  22, 25, 80, 95, 99])}"
            )
            logger.info(f"Filtering done in {time.time() - t_start:.2f} seconds")
            logger.info(
                f"Percentage of removed files: {np.round((old_size - len(ds))*100/old_size, 2)}%"
            )
            new_size_gb = sum(ds["size"])
            logger.info(
                f"Dataset size before {filter} filtering: {old_size} examples, {old_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"Dataset size after {filter} filtering: {len(ds)} examples, {new_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"Percentage of volume removed {np.round((old_size_gb - new_size_gb)*100/old_size_gb, 2)}%"
            )
            dataset = ds

        elif filter == "fertility":
            logger.info(
                f"===== Filtering on tokenizer fertility ratio with thresholds {THRESHOLDS_FERTILITY}====="
            )
            old_size = len(dataset)
            old_size_gb = sum(dataset["size"])
            t_start = time.time()
            ds = dataset.filter(
                filter_tokenizer,
                batched=True,
                batch_size=args.batch_size,
                num_proc=args.num_workers,
            )
            print(
                f"Percentiles of fertility ratio in all dataset: 3rd, 5th, 10th, 95th and 99th: {np.percentile(dataset['fertility_ratio'], [3, 5, 10, 95, 99])}"
            )
            logger.info(f"Filtering done in {time.time() - t_start:.2f} seconds")
            logger.info(
                f"Percentage of removed files: {np.round((old_size - len(ds))*100/old_size, 2)}%"
            )
            new_size_gb = sum(ds["size"])
            logger.info(
                f"Dataset size before {filter} filtering: {old_size} examples, {old_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"Dataset size after {filter} filtering: {len(ds)} examples, {new_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"Percentage of volume removed {np.round((old_size_gb - new_size_gb)*100/old_size_gb, 2)}%"
            )
            dataset = ds

    # Save dataset
    logger.info(
        f"Final dataset has {len(dataset)} samples and {sum(dataset['size']) / 1e9:.2f} GB of code"
    )
    logger.info("===== Saving filtered dataset =====")

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
    logger.info(f"Dataset successfully saved in {time.time() - t_start:.2f} seconds")
