#!/usr/bin/env python
# -*- coding: utf-8 -*-
# author      : Chenghao Mou (mouchenghao@gmail.com)
# created     : 10/21/2022
from __future__ import annotations

import glob
import logging
import multiprocessing
import os
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, Set

import pandas as pd

multiprocessing.set_start_method("fork", force=True)

import numpy as np
import typer
from datasets import Dataset, Features, Sequence, Value, concatenate_datasets, load_dataset, load_from_disk
from datasketch import LeanMinHash, MinHash, MinHashLSH
from rich.console import Console
from rich.logging import RichHandler
from tqdm import tqdm

random.seed(42)
MINHASH_SEED = 42
NON_ALPHA = re.compile("[^A-Za-z_0-9]")
console = Console()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(RichHandler(rich_tracebacks=True))
logger.propagate = False


human_eval_lsh: MinHashLSH | None = None
mbpp_lsh: MinHashLSH | None = None

dup_ids: Set[int] = set()

DATASETS_TO_CHECK = [
    {
        "name": "openai_humaneval",
        "splits": ["test"],
        "columns": ["prompt", "canonical_solution", "test"],
        "codename": "human_eval",
        "index": "human_eval_lsh",  # The same name as the global variable
    },
    {
        "name": "mbpp",
        "splits": ["train", "validation", "test"],
        "columns": ["text", "code", "test_list"],
        "codename": "mbpp",
        "index": "mbpp_lsh",  # The same name as the global variable
    },
]


def load_dataset_with_config(conf: Dict[str, Any]) -> Dataset:
    """
    Load a dataset based on the configuration. Be careful about changing this function,
    as it is used for caching the intermediate results.

    Parameters
    ----------
    conf : Dict[str, Any]
        The configuration. Mainly, there are three ways to load a dataset:
        1. Directly from the hub
        2. From a local git repository
        3. From a local dataset directory that was saved by `save_to_disk` before

    Returns
    -------
    Dataset
        The loaded dataset.
    """

    # Load from hub
    if not conf["lfs"]:
        ds = load_dataset(
            conf["dataset"],
            conf["config"],
            data_dir=conf["data_dir"],
            split=conf["split"],
            use_auth_token=True,
            cache_dir=conf["cache_dir"],
        )
    # Or load from git lfs files
    elif not os.path.exists(conf["concat_output"]):
        datasets = []
        # In practice, it might stuck here, you can hit Ctrl+C and run it again.
        for file in tqdm(sorted(glob.glob(conf["data_dir"] + "/*.jsonl")), desc="Loading datasets..."):
            datasets.append(load_dataset("json", data_files=file, split=conf["split"], cache_dir=conf["cache_dir"]))
        ds = concatenate_datasets(datasets)
        ds.save_to_disk(conf["concat_output"])
        ds = load_from_disk(conf["concat_output"])
    # Or load from the concatenated dataset
    else:
        ds = load_from_disk(conf["concat_output"])

    ds = ds.map(
        lambda _, idx: {"__id__": idx},
        with_indices=True,
        num_proc=os.cpu_count(),
        desc="Adding index...",
    )

    return ds


def embed_func(idx: int, content: str, *, num_perm: int) -> Dict[str, Any]:
    """
    Embed the content of a record into a MinHash object. This function should be
    used with multiprocessing and it scales well with the number of cores.

    Parameters
    ----------
    idx : int
        The index of the record.
    content : str
        The content to embed.
    num_perm : int
        The number of permutations to use in the MinHash object.
    seed : int
        The seed to use in the MinHash object.

    Returns
    -------
    Dict[str, Any]
        The MinHash signature and the index of the record.

    Examples
    --------
    >>> result = embed_func(0, "Hello world!", num_perm=128)
    >>> result["__id__"]
    0
    >>> result["__signature__"].shape
    (128,)
    >>> result["__signature__"].dtype
    dtype('uint64')
    """
    m = MinHash(num_perm=num_perm, seed=MINHASH_SEED)
    m.update_batch([token.encode("utf-8") for token in {t for t in NON_ALPHA.split(content) if t}])
    return {"__signature__": m.hashvalues, "__id__": idx}


def query_func(idx: int, signature: np.ndarray, *, index: MinHashLSH) -> Dict[str, Any]:
    """
    Query the MinHashLSH index for the record. This function can be used with multiprocessing
    as long as the index is shared across processes.

    Parameters
    ----------
    index : MinHashLSH
        The MinHashLSH index. It is shared across all processes when using multiprocessing with fork without copy.
    record : Dict[str, Any]
        The record to query.

    Returns
    -------
    Dict[str, Any]
        The query result.
    """
    return {
        "__neighbors__": [
            str(dup_idx)
            for dup_idx in index.query(
                LeanMinHash(seed=MINHASH_SEED, hashvalues=signature),
            )
        ],
        "__id__": idx,
    }


def jaccard_similarity(code1: str, code2: str) -> float:
    """
    Calculate the jaccard similarity between two code snippets.

    Parameters
    ----------
    code1 : str
        The first code snippet.
    code2 : str
        The second code snippet.

    Returns
    -------
    float
        The jaccard similarity between the two code snippets.

    Examples
    --------
    >>> jaccard_similarity("a = 1", "a = 2")
    0.3333333333333333
    >>> jaccard_similarity("a = 1", "a = 1")
    1.0
    """
    tokens1 = set([t for t in NON_ALPHA.split(code1) if t.strip()])
    tokens2 = set([t for t in NON_ALPHA.split(code2) if t.strip()])
    return len(tokens1 & tokens2) / max(1, len(tokens1 | tokens2))


if __name__ == "__main__":

    def run(
        dataset: str = typer.Option("codeparrot/codeparrot-clean-valid", help="The dataset to use"),
        config: str = typer.Option("default", help="Dataset config"),
        data_dir: str = typer.Option(None, help="Dataset data directory"),
        split: str = typer.Option("train", help="Dataset split"),
        column: str = typer.Option("content", help="Dataset column"),
        cache_dir: str = typer.Option(".cache", help="Cache directory"),
        num_perm: int = typer.Option(128, help="Number of permutations"),
        seed: int = typer.Option(42, help="Random seed"),
        threshold: float = typer.Option(0.58, help="Minhash threshold"),
        verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
        output: str = typer.Option(None, help="Store the deduplicated dataset"),
        lfs: bool = typer.Option(False, help="Use LFS files"),
    ):
        global dup_ids

        OUTPUT_BASE = Path("results") / dataset / config / (data_dir or "all") / split / column
        OUTPUT_BASE.mkdir(exist_ok=True, parents=True)
        output_concat = OUTPUT_BASE / "concat"
        output = output or (OUTPUT_BASE / "decontaminated")
        output_duplicates = OUTPUT_BASE / "duplicates"
        output_duplicate_results = OUTPUT_BASE / "duplicate_results.jsonl"
        logger.info(f"{'Output base':<30}: {OUTPUT_BASE}")
        logger.info(f"{'Output concat':<30}: {output_concat}")
        logger.info(f"{'Output duplicates':<30}: {output_duplicates}")
        logger.info(f"{'Output duplicate results':<30}: {output_duplicate_results}")
        logger.info(f"{'Output':<30}: {output}")

        conf = {
            "cache_dir": cache_dir,
            "num_perm": num_perm,
            "seed": seed,
            "threshold": threshold,
            "dataset": dataset,
            "config": config,
            "data_dir": data_dir,
            "split": split,
            "column": column,
            "verbose": verbose,
            "output": output,
            "lfs": lfs,
            "concat_output": output_concat,
        }

        time_measures = {}

        for benchmark in DATASETS_TO_CHECK:
            globals()[benchmark["index"]] = MinHashLSH(
                threshold=conf["threshold"],
                num_perm=conf["num_perm"],
            )
        time_measures["load_dataset"] = time.time()
        ds = load_dataset_with_config(conf)
        time_measures["load_dataset"] = time.time() - time_measures["load_dataset"]
        DATA_SIZE = len(ds)
        start_time = time.time()

        embedded = ds.map(
            function=embed_func,
            fn_kwargs={"num_perm": conf["num_perm"]},
            input_columns=["__id__", conf["column"]],
            remove_columns=[conf["column"]],
            num_proc=os.cpu_count(),
            desc=f"Fingerprinting...",
        )

        duplicate_results = []
        for _, benchmark in enumerate(DATASETS_TO_CHECK):
            benchmark_ds = concatenate_datasets(
                [
                    load_dataset(benchmark["name"], split=split, cache_dir=conf["cache_dir"])
                    for split in benchmark["splits"]
                ]
            )
            benchmark_ds = benchmark_ds.map(
                function=lambda x, idx: {
                    **embed_func(
                        idx,
                        " ".join(
                            [x[col] if isinstance(x[col], str) else " ".join(x[col]) for col in benchmark["columns"]]
                        ),
                        num_perm=conf["num_perm"],
                    ),
                    "__content__": " ".join(
                        [x[col] if isinstance(x[col], str) else " ".join(x[col]) for col in benchmark["columns"]]
                    ),
                },
                num_proc=os.cpu_count(),
                with_indices=True,
                desc=f"Fingerprinting...",
            )
            with globals()[benchmark["index"]].insertion_session() as session:
                for record in benchmark_ds:
                    session.insert(record["__id__"], LeanMinHash(seed=MINHASH_SEED, hashvalues=record["__signature__"]))

            queried = embedded.map(
                function=lambda x, y: query_func(x, y, index=globals()[benchmark["index"]]),
                num_proc=os.cpu_count(),
                input_columns=[
                    "__id__",
                    "__signature__",
                ],
                remove_columns=["__signature__"],
                desc="Querying...",
                features=Features(
                    {
                        "__id__": Value("uint64"),
                        "__neighbors__": Sequence(Value("string")),
                    }
                ),
            ).filter(
                lambda x: len(x["__neighbors__"]) > 0,
                num_proc=os.cpu_count(),
                desc=f"Filtering...",
            )

            for record in tqdm(
                queried,
                desc=f"Checking for false positives...",
            ):
                neighbors = set(record["__neighbors__"])
                curr_text = ds[record["__id__"]][conf["column"]]
                for neighbor in neighbors:
                    reference = benchmark_ds[int(neighbor)]
                    reference_text = reference["__content__"]
                    if jaccard_similarity(curr_text, reference_text) >= conf["threshold"]:
                        break
                else:
                    continue
                dup_ids.add(record["__id__"])
                duplicate_results.append(
                    {
                        "original_record": ds[record["__id__"]],
                        "duplicate_dataset": benchmark["name"],
                        "duplicate_ids": [benchmark_ds[int(neighbor)] for neighbor in neighbors],
                    }
                )

            logger.info(f"Done querying false positives for {benchmark['name']}")

            if benchmark["name"] == "openai_humaneval":
                if "repository_name" not in ds.features or "path" not in ds.features:
                    break
                logger.info("Checking HumanEval")
                KNOWN_PATH = "LaudateCorpus1/code-align-evals-data/human_eval"
                subset = ds.filter(
                    lambda x: KNOWN_PATH in x["repository_name"] + "/" + x["path"],
                    num_proc=os.cpu_count(),
                    desc=f"Filtering for HumanEval...",
                )
                # Find out the minimum maximum similarity
                thresholds = []
                for record in subset:
                    thresholds.append(0)
                    for target in benchmark_ds:
                        thresholds[-1] = max(
                            thresholds[-1], jaccard_similarity(record[conf["column"]], target["__content__"])
                        )

                logger.info(f"{'Minimum maximum similarity':<30}: {min(thresholds):.3f}")
                logger.info(f"{'Maximum maximum similarity':<30}: {max(thresholds):.3f}")
                logger.info(f"{'Mean maximum similarity':<30}: {np.mean(thresholds):.3f}")

            logger.info(f"Finished checking benchmark {benchmark['name']}")

        time_measures["total_processing_time"] = time.time() - start_time

        duplicates = ds.filter(lambda x: x["__id__"] in dup_ids, num_proc=os.cpu_count())
        final_data = ds.filter(
            lambda idx: idx not in dup_ids,
            input_columns=["__id__"],
            num_proc=os.cpu_count(),
            desc="Filtering duplicates...",
        )

        final_data.save_to_disk(output)
        duplicates.save_to_disk(output_duplicates)
        pd.DataFrame(duplicate_results).to_json(output_duplicate_results, lines=True, orient="records")

        FINAL_DATA_SIZE = len(final_data)
        DUP_SIZE = DATA_SIZE - FINAL_DATA_SIZE
        LAN = (data_dir or "all").split("/")[-1]

        logger.info(f"{'Language':<30}: {LAN}")
        logger.info(f"{'Data Number':<30}: {DATA_SIZE}")
        logger.info(f"{'Duplicate Number':<30}: {DUP_SIZE}")
        logger.info(f"{'Duplicate Rate':<30}: {DUP_SIZE / DATA_SIZE:.2%}")
        logger.info(f"{'Total Time':<30}: {time.time() - start_time:.2f} seconds")

    typer.run(run)
