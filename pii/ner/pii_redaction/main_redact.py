"""Mask detected PII in a dataset.
"""

import argparse
import json
import logging
import random
import time
from functools import partial
from pprint import pformat

from datasets import load_dataset
from datasets.utils.logging import set_verbosity_info

from manual_sharding import save_manual_shards
from utils import get_replacements, redact_pii_batch


def parseArgs():
    parser = argparse.ArgumentParser(description="PII detection and redaction")
    parser.add_argument(
        "--dataset_name",
        default="bigcode/pii-for-code",
        type=str,
        help="HF repo name/path of the dataset.",
    )
    parser.add_argument(
        "--num_load_proc",
        default=64,
        type=int,
        help="Number of processes to use for loading the dataset",
    )
    parser.add_argument(
        "--text_column",
        default="content",
        type=str,
        help="Text column to use, if will be renamed to content",
    )
    parser.add_argument(
        "--split",
        default="train",
        type=str,
        help="Dataset split to process",
    )
    parser.add_argument(
        "--batch_size",
        default=100,
        type=int,
        help="Batch size for the PII detection/redaction",
    )
    parser.add_argument(
        "--seed",
        default=0,
        type=int,
        help="Seed for random",
    )
    parser.add_argument(
        "--num_proc",
        default=96,
        type=int,
        help="Number of processes to use for the PII detection/redaction",
    )
    parser.add_argument(
        "--no_redaction",
        action="store_true",
        help="If set, we don't perform redaction",
    )
    parser.add_argument(
        "--load_replacements",
        default=True,
        help="If set, we load the replacements from file replacements.json",
    )
    parser.add_argument(
        "--add_reference_text",
        default=True,
        type=bool,
        help="If True we add the reference text with PII between delimiters \
        in the redacted text -used for visualization-",
    )
    parser.add_argument(
        "--check_all_files",
        action="store_true",
        help="If set, we check all files, not only the ones that contain PII",
    )
    parser.add_argument(
        "--check_sampling_size",
        default=0,
        type=int,
        help="Number of samples to check for PII",
    )
    # for saving the dataset: either push to HF or save locally with datasets or save manual shards
    parser.add_argument(
        "--save_mode",
        default="manual_shards",
        type=str,
        choices=["hub", "local", "manual_shards"],
        help="How to save the dataset",
    )
    parser.add_argument(
        "--save_mode_checks",
        default="hub",
        type=str,
        choices=["hub", "local", "manual_shards"],
        help="How to save the  checks dataset",
    )
    # add argument for name of dataset on the hub
    parser.add_argument(
        "--target_dataset",
        default="bigcode-pii2",
        type=str,
        help="HF repo name of the target dataset in save_mode=hub.",
    )
    parser.add_argument(
        "--hub_username",
        default="loubnabnl",
        type=str,
        help="Username for the hub",
    )
    parser.add_argument(
        "--save_path_disk",
        default="bigcode-pii2-local",
        type=str,
        help="Path to save the dataset on disk in save_mode=local.",
    )
    return parser.parse_args()


def get_check_ds(ds, args):
    if not args.check_all_files:
        ds_checks = ds.filter(
            lambda exs: exs["modified"],
            batched=True,
            batch_size=args.batch_size,
            num_proc=args.num_proc,
        )
    else:
        ds_checks = ds
    if not args.check_sampling_size:
        sampling_size = len(ds_checks)
    idx_samples = random.sample(
        range(len(ds_checks)), min(len(ds_checks), sampling_size)
    )
    ds_checks = ds_checks.select(idx_samples)

    return ds_checks


def check_uniques(example, uniques):
    """Check if current id is still in set of unique id and remove if true."""
    if example["id"] in uniques:
        uniques.remove(example["id"])
        return True
    else:
        return False


def main():
    set_verbosity_info()
    args = parseArgs()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logging.basicConfig(
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%m/%d/%Y %H:%M:%S",
        level=logging.INFO,
        handlers=[logging.FileHandler(f"logs/pii-{args.dataset_name.split('/')[-1]}.log"), logging.StreamHandler()],
    )
    logger.info(
        f"** The job is running with the following arguments: **\n{args}\n **** "
    )

    logger.info(f" ===== Loading {args.dataset_name} =====")
    ds = load_dataset(
        args.dataset_name,
        split=args.split,
        use_auth_token=True,
        num_proc=args.num_load_proc,
    )
    if args.text_column != "content":
        ds = ds.rename_column(args.text_column, "content")

    logger.info(f" ===== Deduplicating dataset =====")
    # Deduplication based on ids
    uniques = set(ds["id"])
    frac = len(uniques) / len(ds)
    logger.info(f"Fraction of duplicates: {1-frac:.2%}")
    logger.info(f"Dataset:\n{ds}")
    # Deduplicate data and apply heuristics
    t_start = time.time()
    ds_pii = ds.filter(check_uniques, fn_kwargs={"uniques": uniques})
    logger.info(f"Time to filter dataset: {time.time()-t_start:.2f}")
    logger.info(f"Dataset after dedup:\n{ds_pii}")

    logger.info(
        f"Number of samples that contained PII: {sum([1 if x['entities'] else 0 for x in ds_pii])}"
    )
    logger.info(
        f"Total number of secrets found: {sum([len(x['entities']) for x in ds_pii])}"
    )

    # redact PII in the dataset
    logger.info(f" ===== Applying PII redaction =====")
    random.seed(args.seed)

    replacements = get_replacements()
    with open("replacements.json", "w") as f:
        json.dump(replacements, f)
    logging.info(f"Using the following replacements:\n{pformat(replacements)}")
    ds_pii = ds_pii.map(
        partial(
            redact_pii_batch,
            replacements=replacements,
            add_references=args.add_reference_text,
        ),
        batched=True,
        batch_size=args.batch_size,
        num_proc=args.num_proc,
        load_from_cache_file=False,
    )
    logging.info(f"Dataset info after PII redaction:\n{ds_pii}")

    # check the dataset
    logger.info(
        f" ===== Checking {args.check_sampling_size} samples from those modified in the dataset ====="
    )
    ds_checks = get_check_ds(ds_pii, args)

    # save checks dataset
    if len(ds_checks) == 0:
        logger.info("Dataset was empty. Not saving anything.")
    else:
        logger.info(f"Checks dataset info {ds_checks}")
        if args.save_mode_checks == "hub":
            logger.info(
                f"Pushing the checks dataset to the Hub as {args.target_dataset}_checks"
            )
            ds_checks.push_to_hub(args.target_dataset + "_checks")

        elif args.save_mode_checks == "local":
            logger.info(f"Saving the checks dataset to disk")
            ds_checks.save_to_disk(args.save_path_disk + "_checks")

        elif args.save_mode_checks == "manual_shards":
            logger.info(f"Saving the checks dataset in manual shards")
            save_manual_shards(
                ds_checks,
                user=args.hub_username,
                remote_dataset_repo=args.target_dataset + "_checks",
            )

    logger.info("Removing columns that are not needed for the final dataset")
    columns = ["content", "modified", "entities"]
    if args.add_reference_text:
        columns.append("references")
    ds_pii = ds_pii.remove_columns(columns)
    ds_pii = ds_pii.rename_column("new_content", "content")
    logger.info(f"Dataset info after removing columns:\n{ds_pii}")

    # save the final dataset
    if args.save_mode == "hub":
        logger.info(
            f" ===== Pushing the dataset to the Hub as: {args.target_dataset} ====="
        )
        ds_pii.push_to_hub(args.target_dataset)

    elif args.save_mode == "local":
        logger.info(f" ===== Saving the dataset to disk =====")
        ds_pii.save_to_disk(args.save_path_disk)

    elif args.save_mode == "manual_shards":
        logger.info(f" ===== Saving the dataset in manual shards =====")
        save_manual_shards(
            ds_pii, user=args.hub_username, remote_dataset_repo=args.target_dataset
        )

    logger.info(f" ===== Dataset saved successfully =====")


if __name__ == "__main__":
    main()
