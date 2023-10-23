import argparse
from functools import partial
import json
import logging
import random

from datasets import load_from_disk
from utils.manual_sharding import save_manual_shards
from transformers import PreTrainedTokenizerFast


NUM_PROC = 32
log_file = "/data/the_stack_v2/repo_level.log"

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
    level=logging.INFO,
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)


def extract_dict(repo):
    return {
        "files": json.loads(repo['dict_rep'])
    }


def has_meta(file_content):
    return file_content.startswith("<filename>") or file_content.startswith("<reponame>") or file_content.startswith("<gh_stars>")


def split_meta_prefix(file):
    file_content = file['content_with_meta']
    # Remove the first line if it is meta-information
    if has_meta(file_content):
        meta, file_content = file_content.split("\n", 1)
    else:
        meta = ""
    assert not has_meta(file_content)
    return {
        "content": file_content,
        "meta": meta,
        "path": file['path'],
        # "repo_name": file["repo_name"]
    }


def split_meta(repo):
    return {
        "files": [
            split_meta_prefix(f)
            for f in repo['files']
        ]
    }

def file_content(file):
    return f"<filename>{file['path']}\n{file['content']}"


def repo_content(repo, order):
    # Order files by path
    if order == "Random":
        ordered_files = random.sample(repo['files'], k=len(repo['files']))
    elif order == "Depth-first":
        ordered_files = sorted(repo['files'], key=lambda f: f['path'])
    elif order == "Breadth-first":
        ordered_files = sorted(repo['files'], key=lambda f: f['path'].count("/"))
    elif order == "Top-level+Depth-first":
        top_files = sorted([f for f in repo['files'] if f['path'].count("/")==1], key=lambda f: f['path'])
        other_files = sorted([f for f in repo['files'] if f['path'].count("/")!=1], key=lambda f: f['path'])
        ordered_files = top_files + other_files
    else:
        raise ValueError(f"Unknown order: {order}")
    # print(f"File order:\n{[f['path'] for f in ordered_files]}")
    # Concatenate files
    repo_content = ''.join([file_content(f) for f in ordered_files])
    return {
        "content": f"<reponame>{repo['repo_name']}{repo_content}",
    }


parser = argparse.ArgumentParser()
parser.add_argument("--out_path", type=str, default="/data/the_stack_v2/repo_level")
args = parser.parse_args()

grouped = load_from_disk("/data/the_stack_v2/grouped")
logger.info(f"Loaded from disk: {len(grouped)}")

ds = grouped.map(extract_dict, remove_columns=["dict_rep"], num_proc=NUM_PROC)
logger.info(f"Extracted dicts: {len(ds)}")
ds = ds.map(split_meta, num_proc=NUM_PROC)
logger.info(f"Splitted meta: {len(ds)}")

for order in ["Random", "Depth-first", "Breadth-first", "Top-level+Depth-first"]:
    out_path = f"{args.out_path}/{order}"
    ds_order = ds.map(partial(repo_content, order=order), remove_columns=["files"], num_proc=NUM_PROC)
    logger.info(f"Created repo content ({order}): {len(ds_order)}")
    save_manual_shards(
        ds_order, user="bigcode", remote_dataset_repo=f"python_repo_level_{order}", out_path=out_path, subset=""
    )
    logger.info(f"Dataset ({order}) successfully saved at {out_path}")
