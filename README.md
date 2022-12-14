# BigCode Dataset

This repository gathers all the code used to build the BigCode datasets such as [The Stack](https://huggingface.co/datasets/bigcode/the-stack) as well as the preprocessing 
necessary used for model training.

## Contents

- `language_selection`: notebooks and file with language to file extensions mapping used to build the Stack v1.1.
- `pii`: code for running PII detection and anonymization on code datasets.
- `preprocessing`: code for filtering code datasets based on:
  - line length and percentage of alphanumeric characters.
  - number of stars.
  - comments to code ratio.
  - tokenizer fertility
