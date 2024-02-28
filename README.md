# BigCode Dataset

This repository gathers all the code used to build the BigCode datasets such as [The Stack](https://huggingface.co/datasets/bigcode/the-stack) as well as the preprocessing 
necessary used for model training.

## Contents

- `language_selection`: notebooks and file with language to file extensions mapping used to build the Stack v1.1.
- `pii`: code for running PII detection and anonymization on code datasets.
- `decontamination`: script to remove files that match test-samples from code generation benchmarks.
- `preprocessing`: code for filtering code datasets based on:
  - line length and percentage of alphanumeric characters (basic filter)
  - number of stars, comments to code ratio, tokenizer fertility
  - Additional filters used for StarCoder Training:
    - basic-filter with parameters that depend on the file's extension.
    - filter to remove XML files
    - filter for HTML based on displayed-text VS code ratio
    - filter to remove small and large files (for json and yaml)
    - code to generate full-content with meta (repo-name, filename, num stars) for training
  - Filters for GitHub Issues
  - Filters for Git Commits
  - Code to convert Jupyter notebooks to scripts
  - Code to convert Jupyter notebooks to structured markdown-code-output triplets
