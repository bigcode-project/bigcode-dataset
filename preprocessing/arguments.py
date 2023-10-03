from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FilteringArguments:
    # add arguments in the following format
    dataset_name: Optional[str] = field(
        default="bigcode/python_permissive",
        metadata={"help": "HF repo name/path of the dataset."},
    )
    subset: Optional[str] = field(
        default="data/",
        metadata={"help": "Data subset."},
    )
    split: Optional[str] = field(
        default="train",
        metadata={"help": "Dataset split to process."},
    )
    tokenizer_name: Optional[str] = field(
        default="bigcode/digit-bytelevel-bpe-jss-v1.1-49152",
        metadata={"help": "HF repo name/path of the tokenizer."},
    )
    line_max: Optional[int] = field(
        default=1000,
        metadata={"help": "Max line length allowed"},
    )
    line_mean: Optional[int] = field(
        default=100,
        metadata={"help": "Mean line length allowed"},
    )
    alpha_frac: Optional[float] = field(
        default=0.25,
        metadata={"help": "Minimum fraction of alphanumeric characters allowed."},
    )
    min_threshold_comments: Optional[float] = field(
        default=0.01,
        metadata={"help": "Minimum threshold for comment to code ratio."},
    )
    max_threshold_comments: Optional[float] = field(
        default=0.8,
        metadata={"help": "Maximum threshold for comment to code ratio."},
    )
    threshold_stars: Optional[int] = field(
        default=5,
        metadata={"help": "Minimum threshold for number of stars."},
    )
    min_size: Optional[int] = field(
        default=100,
        metadata={"help": "Minimum content size."},
    )
    max_size: Optional[int] = field(
        default=5000,
        metadata={"help": "Maximum content size."},
    )
    per_extension_filter_csv: Optional[str] = field(
        default=None,
        metadata={"help": "Path to csv file containing the filters to be applied depending on file extension"},
    )
    num_workers: Optional[int] = field(
        default=96,
        metadata={"help": "Number of workers for multiprocessing."},
    )
    batch_size: Optional[int] = field(
        default=1000,
        metadata={"help": "Batch size for multiprocessing."},
    )
    push_to_hub: Optional[bool] = field(
        default=False,
        metadata={"help": "Push the dataset to the Hub."},
    )
    remote_repo: Optional[str] = field(
        default="stack-pjj-stars-filtering",
        metadata={"help": "HF repo name of the target dataset in the hub."},
    )
    hub_username: Optional[str] = field(
        default="loubnabnl",
        metadata={"help": "Username for the hub."},
    )
    out_path: Optional[str] = field(
        default=None,
        metadata={"help": "Local path to save the ouptut dataset."},
    )
    log_file: Optional[str] = field(
        default="filtering.log",
        metadata={"help": "File to write log to."},
    )
    fix_license_columns: Optional[bool] = field(
        default=False,
        metadata={"help": "Fix license columns."},
    )
    run_decontamination: Optional[bool] = field(
        default=False,
        metadata={"help": "Run decontamination after the filtering"},
    )
    add_metadata: Optional[bool] = field(
        default=False,
        metadata={"help": "Run add_content_with_meta after the filtering and decontamination"},
    )

@dataclass
class ContentWithMetaArguments:
    # add arguments in the following format
    dataset_name: Optional[str] = field(
        default="bigcode/the-stack-smol",
        metadata={"help": "HF repo name/path of the dataset."},
    )
    subset: Optional[str] = field(
        default="data/java",
        metadata={"help": "Data subset."},
    )
    split: Optional[str] = field(
        default="train",
        metadata={"help": "Datasset split to process."},
    )
    add_repo_name_prob: float = field(
        default=.2,
        metadata={"help": "Probability to add repo-name"}
    )
    add_file_name_prob: float = field(
        default=.2,
        metadata={"help": "Probability to add filename"}
    )
    add_num_stars_prob: float = field(
        default=.2,
        metadata={"help": "Probability to add number of stars"}
    )
    num_workers: Optional[int] = field(
        default=96,
        metadata={"help": "Number of workers for multiprocessing."},
    )
    batch_size: Optional[int] = field(
        default=1000,
        metadata={"help": "Batch size for multiprocessing."},
    )
    push_to_hub: Optional[bool] = field(
        default=False,
        metadata={"help": "Push the dataset to the Hub."},
    )
    remote_repo: Optional[str] = field(
        default="stack-pjj-stars-filtering",
        metadata={"help": "HF repo name of the target dataset in the hub."},
    )
    hub_username: Optional[str] = field(
        default="loubnabnl",
        metadata={"help": "Username for the hub."},
    )
    out_path: Optional[str] = field(
        default=None,
        metadata={"help": "Local path to save the ouptut dataset."},
    )
    log_file: Optional[str] = field(
        default="filtering.log",
        metadata={"help": "File to write log to."},
    )
