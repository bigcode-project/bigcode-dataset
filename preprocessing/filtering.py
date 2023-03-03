"""Filter code datasets using:  
    * basic filters (line length and alphanumeric characters)
    * comments to code ratio (maximum + minimum)
    * minimum number of stars
    * tokenizer fertility ratio (char to token ratio)"""

import fnmatch
import logging
import time
from functools import partial
import csv

import numpy as np
from datasets import load_dataset
from datasets.utils.logging import set_verbosity_info
from transformers import AutoTokenizer, HfArgumentParser

from arguments import FilteringArguments
from utils.manual_sharding import save_manual_shards
from utils.text_extraction import get_nl_ratio

# define list of filters to apply
ALL_FILTERS = ["basic", "basic_per_extension", "stars", "comments", "fertility", "xml", "html"]
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


def basic_filters_per_extension(example, ext_to_filter):
    """Filter files based on line length and % alphanumeric characters.
    The filtering parameters depend on the file extension, given by `ext_to_filter`"""
    # Get the filter-params we want to use
    # extension `None` is an empty string in the csv
    try:
        (include, line_max, line_mean, alphanum_frac, alphabetic_frac) = ext_to_filter[(language_format_from_dataset(
            example["lang"]), example["ext"] if example["ext"] is not None else ""
        )]
    except KeyError as e:
        # Some extensions are not in the csv. This happens for dockerfiles.
        # Exclude these files
        logging.error(str(e) + f":{example['ext']} not in ext_to_filter")
        include = False
    if not include:
        return False
    if line_max and example["max_line_length"] > line_max:
        return False
    elif line_mean and example["avg_line_length"] > line_mean:
        return False
    # Filter files with low percentage of alphanumeric chars
    elif alphanum_frac and example["alphanum_fraction"] < alphanum_frac:
        return False
    # Filter files with low percentage of alphabetic chars
    elif alphabetic_frac and sum(map(str.isalpha, example['content'])) < alphabetic_frac * len(example['content']):
        return False
    return True


def language_format_from_dataset(lang: str):
    """Convert: Language field in dataset -> language field in csv file that defines the filters."""
    # TODO: other special cases?
    if lang == "C#":
        return "c-sharp"
    if lang == "F#":
        return "f-sharp"
    return lang.lower().replace(" ", "-")

def language_format_from_data_dir(lang: str):
    """Convert: Language subset name in dedup data -> language field in csv file that defines the filters."""
    if lang == "cpp":
        return "c++"
    return lang


def language_format_from_csv_to_data_dir(lang: str):
    """Convert: language field in csv -> Language subset name in dedup data"""
    if lang == "c++":
        return "cpp"
    return lang


def get_filter_params(row: dict):
    """Extract filter parameters from csv row"""
    include = row["Include"] == "1"
    try:
        line_max = int(row["Long_line_threshold"])
    except ValueError:
        line_max = None
    line_mean = 100 if line_max else None
    try:
        alphanum_frac = float(row["Alphanum_threshold"])
    except ValueError:
        alphanum_frac = None
    try:
        alphabetic_frac = float(row["Alpha filter"])
    except ValueError:
        alphabetic_frac = None
    return include, line_max, line_mean, alphanum_frac, alphabetic_frac


def load_filter_csv(path: str, language: str = None):
    """Load csv file that specifies the filter to apply for each (lang, extension).
    TODO: add some tests. Check that filters are correctly set."""
    # (Lang, extension) -> filter_args
    ext_to_filter = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            # Only take the rows corresponding to the language if specified
            if language is None or row["language"] == language:
                ext_to_filter[(row["language"], row["extension"])] = get_filter_params(row)
    assert len(ext_to_filter) > 0, f"Did not find filtering params corresponding to language: `{language}` in: {path}"
    return ext_to_filter


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


def filter_xml(example):
    """Filter-out XML files"""
    return not ('<?xml version=' in example['content'][:100])


def filter_html(example):
    """Filter HTML files based on displayed text VS code ratio"""
    assert example["lang"] == "HTML", "Filter is only for html examples"
    html = example["content"]
    try:
        soup = BeautifulSoup(html, features="html.parser")
    except TypeError:
        return False

    # kill all script and style elements
    for script in soup(["script", "style"]):
        script.extract()    # rip it out

    # get text
    text = soup.get_text()
    ratio = len(text)/len(html)
    return ratio>0.2  and len(text)>100



def get_size_text(example):
    return {"size": len(example["content"])}


LICENSE_COLUMNS = ['max_stars_repo_licenses', 'max_issues_repo_licenses', 'max_forks_repo_licenses']
def fix_license_cols(example):
    for col in LICENSE_COLUMNS:
        example[col] = [x["item"] for x in example[col]["list"]]
    return example


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
    if args.fix_license_columns:
        dataset = dataset.map(fix_license_cols, num_proc=args.num_workers)
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
        
        elif filter == "basic_per_extension":
            assert args.per_extension_filter_csv is not None
            language = language_format_from_data_dir(args.subset.split("/")[-1]) if args.subset is not None else None
            logger.info(
                f"===== Language: {language}. Basic filtering with line_max, avg_line, alphanum_frac and alphabetic_frac given by : {args.per_extension_filter_csv} ====="
            )
            logger.info(
                f""
            )
            ext_to_filter = load_filter_csv(args.per_extension_filter_csv, language=language)
            logger.info(
                f"Loaded the following filters-per-extension: {ext_to_filter}"
            )
            old_size = len(dataset)
            old_size_gb = sum(dataset["size"])
            t_start = time.time()
            ds = dataset.filter(partial(basic_filters_per_extension, ext_to_filter=ext_to_filter))
            logger.info(f"{filter} Filtering done in {time.time() - t_start:.2f} seconds")
            logger.info(
                f"{filter} Percentage of removed files: {np.round((old_size - len(ds))*100/old_size, 2)}%"
            )
            new_size_gb = sum(ds["size"])
            logger.info(
                f"Dataset size before {filter} filtering: {old_size} examples, {old_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"Dataset size after {filter} filtering: {len(ds)} examples, {new_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"{filter} Percentage of volume removed {np.round((old_size_gb - new_size_gb)*100/old_size_gb, 2)}%"
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

        elif filter == "xml":
            logger.info(
                f"===== Filtering out XML files ====="
            )
            old_size = len(dataset)
            old_size_gb = sum(dataset["size"])
            t_start = time.time()
            ds = dataset.filter(
                filter_xml,
                # batched=True,
                # batch_size=args.batch_size,
                # num_proc=args.num_workers,
            )
            logger.info(f"{filter} Filtering done in {time.time() - t_start:.2f} seconds")
            logger.info(
                f"{filter} Percentage of removed files: {np.round((old_size - len(ds))*100/old_size, 2)}%"
            )
            new_size_gb = sum(ds["size"])
            logger.info(
                f"Dataset size before {filter} filtering: {old_size} examples, {old_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"Dataset size after {filter} filtering: {len(ds)} examples, {new_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"{filter} Percentage of volume removed {np.round((old_size_gb - new_size_gb)*100/old_size_gb, 2)}%"
            )
            dataset = ds

        elif filter == "html":
            from bs4 import BeautifulSoup
            logger.info(
                f"===== Filtering out HTML files ====="
            )
            old_size = len(dataset)
            old_size_gb = sum(dataset["size"])
            t_start = time.time()

            ds = dataset.filter(
                filter_html,
                num_proc=args.num_workers,
            )
            logger.info(f"{filter} Filtering done in {time.time() - t_start:.2f} seconds")
            logger.info(
                f"{filter} Percentage of removed files: {np.round((old_size - len(ds))*100/old_size, 2)}%"
            )
            new_size_gb = sum(ds["size"])
            logger.info(
                f"Dataset size before {filter} filtering: {old_size} examples, {old_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"Dataset size after {filter} filtering: {len(ds)} examples, {new_size_gb / 1e9:.2f} GB"
            )
            logger.info(
                f"{filter} Percentage of volume removed {np.round((old_size_gb - new_size_gb)*100/old_size_gb, 2)}%"
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
    try:
        save_manual_shards(
            dataset, user=args.hub_username, remote_dataset_repo=args.remote_repo, out_path=args.out_path,  subset=args.subset
        )
        logger.info(f"Dataset successfully saved at {args.out_path}/{args.subset} in {time.time() - t_start:.2f} seconds")
    except FileExistsError:
        logger.warning(f"Output dir already exists at {args.out_path}/{args.subset}. Will not save filtered data")

    # Run decontamination
    if args.run_decontamination:
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
        from decontamination.find_substrings import SubstringFilterer

        output_dir_decontaminated = f"{args.out_path}_decontaminate/{args.subset}"

        filterer = SubstringFilterer(
            output_dir=output_dir_decontaminated,
            cached_decontamination_dir=None,  # no previous cached run
            split_languages=False,
            cache_retrieval_key="",
            data_dir=output_dir_decontaminated
        )

        filtered = filterer.run(dataset, args.num_workers, args.batch_size)

        filtered_size_gb = sum(filtered["size"])
        logger.info(
            f"Removed {len(dataset) - len(filtered)} / {len(dataset)} files"
        )
        logger.info(
            f"Dataset size after decontamination: {len(filtered)} examples, {filtered_size_gb / 1e9:.2f} GB"
        )
