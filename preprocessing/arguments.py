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
