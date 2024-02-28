"""
Extract data statistics once filtering.py has finished

number and % of file/volume removed for each language and filter.
Final size/number of files.

Number and list of unrecognized extensions.
"""

from collections import Counter
from pathlib import Path
import re
import json


PER_FILTER_PATTERNS = {
    "num_files_before": r" - Dataset size before (?!any)(\S+) filtering: (\d+) examples",
    "num_files_after": r" - Dataset size after (?!any)(\S+) filtering: (\d+) examples",
    "volume_before": r" - Dataset size before (?!any)(\S+) filtering: \d+ examples, ([\d\.]+) GB",
    "volume_after": r" - Dataset size after (?!any)(\S+) filtering: \d+ examples, ([\d\.]+) GB",
    "percent_files_removed": r" - (\S+) Percentage of removed files: ([\d\.]+)%",
    "percent_volume_removed": r" - (\S+) Percentage of volume removed ([\d\.]+)%",
}
OTHER_PATTERNS = {
    "num_files_before_filters": r" - Dataset size before any filtering: (\d+) examples",
    "volume_before_filters": r" - Dataset size before any filtering: \d+ examples, ([\d\.]+) GB",
    "num_files_after_filters": r" - Final dataset has (\d+) samples and [\d\.]+ GB of code",
    "volume_after_filters": r" - Final dataset has \d+ samples and ([\d\.]+) GB of code",
    "num_files_after_decont": r" - Dataset size after decontamination: (\d+) examples, [\d\.]+ GB",
    "volume_after_decont": r" - Dataset size after decontamination: \d+ examples, ([\d\.]+) GB",
}


def find_pattern(pattern, lines, num_filters: int):
    """
    Find multiple occurrences of `pattern` in `lines`.
    `num_filters`: expected number of matches
    """
    assert re.compile(pattern).groups == 2
    matches = [re.search(pattern, l) for l in lines]
    matches = [(match.group(1), match.group(2)) for match in matches if match is not None]
    # deduplicate matches (in case a job was interrupted then restarted)
    matches = list(set(matches))
    assert len(matches) == num_filters, f"Found {len(matches)} lines matching pattern {pattern}, expected {num_filters}."
    return matches


def find_single_pattern(pattern, lines):
    assert re.compile(pattern).groups == 1
    matches = [re.search(pattern, l) for l in lines]
    matches = [m.group(1) for m in matches if m is not None]
    # deduplicate matches (in case a job was interrupted then restarted)
    matches = list(set(matches))
    assert len(matches) == 1, f"Found {len(matches)} lines matching pattern {pattern}, expected 1."
    return matches[0]


def get_stats(log_file: str):
    # json/yaml were run with 3 filters. other languages with 2
    num_filters = 3 if log_file.stem in ['json', 'yaml'] else 2
    stats = {}

    with open(log_file) as f:
        lines = f.readlines()
    # Get before/after stats for each filter
    for stat_name, p in PER_FILTER_PATTERNS.items():
        for filter, stat in find_pattern(p, lines, num_filters):
            if filter not in stats:
                stats[filter] = {}
            stats[filter][stat_name] = stat
    
    # Get global stats
    for stat_name, p in OTHER_PATTERNS.items():
        stats[stat_name] = find_single_pattern(p, lines)

    return stats

def get_unrecognized_ext(log_file: str):
    pattern = r"- \('([^']+)', '([^']+)'\):\S+ not in ext_to_filter"
    res = []
    with open(log_file) as f:
        for line in f:
            m = re.search(pattern, line)
            if m is not None:
                res.append(m.group(2))
    # Count each occurrence
    res = dict(Counter(res))
    return res

def main():
    logs_path = Path("/data/hf_repos/the_stack_march_training/logs/")
    log_files = list(logs_path.glob("*.log"))
    stats = {
        f.stem: get_stats(f) for f in log_files
    }
    # print(stats)

    with open("preprocessing/statistics/stats.json", "w") as f:
        json.dump(stats, f, indent=4)

    unrecognized = {
        f.stem: get_unrecognized_ext(f) for f in log_files
    }
    
    unrecognized = {lang: l for lang, l in unrecognized.items() if len(l) > 0}
    with open("preprocessing/statistics/unrecognized.json", "w") as f:
        json.dump(unrecognized, f, indent=4)

if __name__ == "__main__":
    main()
