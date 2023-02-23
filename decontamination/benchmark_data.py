
"""data to filter out of the dataset"""
import json
import itertools
from pathlib import Path

from datasets import load_dataset


MBPP_PATH = "/data/mbpp/mbpp.jsonl"
TEST_IDS = list(range(11, 511))

# HumanEval solutions that are considered simple/generic enough to be kept in the training dataset
HUMAN_EVAL_STRINGS_OK = ['return x + y', 'return len(string)', 'return n**2', 'return ''.join(strings)']

DS_1000_PATH = Path("/data/ds-1000/ds1000_data/")


def extract_ds_1000_prompt(prompt: str):
    if "SOLUTION START" in prompt:
        assert prompt.count("SOLUTION START") == 1
        return prompt.split("SOLUTION START")[0]
    elif "BEGIN SOLUTION" in prompt:
        assert prompt.count("BEGIN SOLUTION") == 1
        return prompt.split("BEGIN SOLUTION")[0]
    else:
        raise ValueError()


def load_ds_1000():
    data = []
    for prompt_file in DS_1000_PATH.glob("*/Insertion/q*/prompt.txt"):
        with open(prompt_file) as f:
            data.append(extract_ds_1000_prompt(f.read()))
    return data

def load_mbpp():
    data = []
    with open(MBPP_PATH) as f:
        for line in f:
            data.append(json.loads(line))
    
    data = [sample for sample in data if sample["task_id"] in TEST_IDS]

    assert len(data) == 500
        
    # Checksum / version issues here
    # dataset = load_dataset("mbpp", split="test")
    return data


def mbpp_docstrings():
    data = load_mbpp()
    return [sample["text"] for sample in data]


def mbpp_solutions():
    data = load_mbpp()
    return [sample["code"] for sample in data]


def extract_docstring(prompt: str) -> str:
    if '"""' in prompt:
        if prompt.count('"""') == 2:
            return prompt.split('"""')[1].strip()
        elif prompt.count('"""') == 4:
            return prompt.split('"""')[3].strip()
        else:
            raise ValueError()
    elif '\'\'\'' in prompt:
        assert prompt.count('\'\'\'') == 2
        return prompt.split('\'\'\'')[1].strip()
    else:
        raise ValueError()


def human_eval_docstrings():
    ds = load_dataset("openai_humaneval", split="test")
    docstrings = [extract_docstring(v['prompt']) for v in ds]
    return docstrings


def apps_solutions():
    """
    Solutions column contains a list of strings
    """
    ds = load_dataset("codeparrot/apps", split="test")
    solutions = [sample["solutions"] for sample in ds if len(sample["solutions"]) > 0]
    res = itertools.chain.from_iterable(json.loads(sample) for sample in solutions)
    return list(res)

def multipl_e_docstrings():
    languages = [ 
        "cpp", "cs", "d", "go", "java", "jl", "js", "lua", "php", "pl", "py", "r", 
        "rb", "rkt", "rs", "scala", "sh", "swift", "ts"
    ]
    # languages = ["py", "java", "js"]
    src_datas = ["humaneval", "mbpp"]
    variations = ["", "-remove"]
    data = []
    for lang in languages:
        for src_data in src_datas:
            for variation in variations:
                if src_data == "mbpp" and variation == "-remove":
                    continue
                ds = load_dataset("nuprl/MultiPL-E", f"{src_data}-{lang}{variation}", split="test")
                data += [sample["prompt"].strip() for sample in ds]
    return data



def load_dataset_column(dataset: str, column: str, split: str, name=None):
    ds = load_dataset(dataset, split=split, name=name)
    res = [sample[column].strip() for sample in ds]
    # Only return non-empty strings
    return [sample for sample in res if len(sample) > 0]


FILTER_OUT = {
    "mbpp_docstrings": mbpp_docstrings(),
    "mbpp_solutions": mbpp_solutions(),
    "human_eval_docstrings": human_eval_docstrings(),
    "human_eval_solutions": [
        s for s in load_dataset_column("openai_humaneval", "canonical_solution", "test")
        if s not in HUMAN_EVAL_STRINGS_OK
    ],
    "apps_docstrings": load_dataset_column("codeparrot/apps", "question", "test"),
    # 115212 examples to filter-out in apps-solutions, which would take way too much time without any hashing trick
    # "apps_solutions": apps_solutions(),
    # MultiPL-E samples are from HumanEval and MBPP: we are already looking for them
    # "multipl-e_docstrings": multipl_e_docstrings(),
    # There is no solution provided with multipl-e
    "gsm8k_questions": load_dataset_column("gsm8k", "question", "test", "main"),
    "ds_1000_prompts": load_ds_1000()
}


for benchmark, values in FILTER_OUT.items():
    print(f"num strings from {benchmark}: {len(values)}")
