
"""data to filter out of the dataset"""
import json
import itertools

from datasets import load_dataset


MBPP_PATH = "/data/mbpp/mbpp.jsonl"
TEST_IDS = list(range(11, 511))

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


def load_dataset_column(dataset: str, column: str, split: str):
    ds = load_dataset(dataset, split=split)
    res = [sample[column].strip() for sample in ds]
    # Only return non-empty strings
    return [sample for sample in res if len(sample) > 0]


FILTER_OUT = {
    "mbpp_docstrings": mbpp_docstrings(),
    "mbpp_solutions": mbpp_solutions(),
    "human_eval_docstrings": human_eval_docstrings(),
    "human_eval_solutions": load_dataset_column("openai_humaneval", "canonical_solution", "test"),
    "apps_docstrings": load_dataset_column("codeparrot/apps", "question", "test"),
    # 115212 examples to filter-out in apps-solutions, which would take way too much time without any hashing trick
    # "apps_solutions": apps_solutions(),
    "multipl-e_docstrings": load_dataset_column("nuprl/MultiPL-E", "prompt", "test"),
    # There is no solution provided with multipl-e
    # "multipl-e_solutions": load_dataset_column("nuprl/MultiPL-E", "", "test"),
}


def filter_file(data, return_matched=False):
    """
    Return True, None if the file should be included in the dataset.
    Otherwise return False and some metadata about the file excluded
    """
    content = data['content'].lower()
    # For each substring, try to find it in the file (case insensitive)
    for benchmark, substrings in FILTER_OUT.items():
        for substring in substrings:
            if substring.lower() in content:
                if return_matched:
                    return False, f"{benchmark}_match", substring
                else:
                    return False, f"{benchmark}_match"

    # Return True, None if none of the substrings was found
    if return_matched:
        return True, None, None
    else:
        return True, None
