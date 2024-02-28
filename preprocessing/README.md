# Filtering The Stack
Three filters for the preprocessing of The Stack are available:

* **basic**: uses line length filtering and percentage of alphanumeric characters (similarly to [Codex](https://arxiv.org/abs/2107.03374)), default thresholds are `max_line_length=1000`, `mean_line_length=100`, `alpha_num_threshold=0.25`.
* **stars**: filter based on number of stars of the file (i.e. of the parent repository), default threshold is `threshold_stars=5`.
* **comments**:  filter based on minimum and maximum comments to code ratio, default thresholds are `min_comments_ratio=0.01`, `max_comments_ratio=0.8` (this filter was used in the preparation of [SantaCoder](https://huggingface.co/bigcode/santacoder) data which included python, Java & JavaScript only):
    * For Python, we extract comments using Python tokenizer and docstrings using `ast` parsing.
    * For other languages (Java and Javascript), we extract comments using `pygments` library.
    * We compute the comment to code ratio of a file by counting the number of characters in comments over the total number of characters in the file.
* **fertility**: filter based on the character to token ratio after calling the tokenizer on the code file. Different thresholds for Python (2.5), Java (2.9) and JavaScript (2.6) for data after near-dedup + basic filtering & PII redaction.

* Additional filters used for StarCoder Training [StarCodeData](https://huggingface.co/datasets/bigcode/starcoderdata):
    - basic-filter with parameters that depend on the file's extension.
    - filter to remove XML files
    - filter for HTML based on displayed-text VS code ratio
    - filter to remove small and large files (for json and yaml)
    - code to generate full-content with meta (repo-name, filename, num stars) for training

Below is an example for running all filters on the java subset of [The-Stack-Smol](https://huggingface.co/datasets/bigcode/the-stack-smol). You can specify the filters to use separated by commas in `--filters` argument:
```bash
python filtering.py --dataset_name bigcode/the-stack-smol --subset data/java --filters basic,comments,stars,fertility --hub_username loubnabnl --remote_repo test_filter_pipeline_java
```
In this case, the dataset is saved in parquet shards in a clone of `remote_repo`. If you want to push the data directly to the hub add `push_to_hub` flag. 

A log file `filtering.log` is saved in the working directory with details about the processing and percentage of files and volume removed at each step.

# Filtering GitHub Issues

We release the filtered GitHub issues dataset as part of [StarCoderData](https://huggingface.co/datasets/bigcode/starcoderdata), and provide the code used to curate the dataset:
```bash
python filtering_issues.py --dataset_name bigcode/subset-github-issues --subset data/ --hub_username loubnabnl --remote_repo test_filter_github_issues
```

# Filtering Git Commits
We release the filtered Git Commits dataset as part of [StarCoderData](https://huggingface.co/datasets/bigcode/starcoderdata), and provide a notebook with the cleaning steps at `filtering_git_commits.ipynb`.

# Converting Jupyter Notebooks to Scripts
We release the Jupyter scripts dataset as part of [StarCoderData](https://huggingface.co/datasets/bigcode/starcoderdata), and provide the code used to curate the dataset:
```bash
python jupyter_script_conversion.py
```

# Creating Jupyter-structured dataset

## Step 1
Parse Jupyter notebooks from `the Stack`.  
```
python jupyter-structured/jupyter-segment-notebooks.py
```

## Step 2
Generate markdown-code-output triplets.
```
python jupyter-structured/jupyter-generate-triplets.py
```

## Step 3
Create notebook-level structured dataset using `jupyter-structured/jupyter-structured.ipynb`.



