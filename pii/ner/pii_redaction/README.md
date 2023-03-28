# PII redaction

```bash
LANG=jupyter-scripts-dedup-filtered
python main_redact.py --dataset_name  /fsx/leandro/data/pii_result/$LANG --target_dataset $LANG-no-pii --save_path_disk $LANG-no-pii-local
```
/fsx/leandro/data/pii_result/jupyter-scripts-dedup-filtered
/fsx/leandro/data/pii_result/jupyter-structured-clean-dedup
/fsx/leandro/data/pii_result/github-issues-filtered-structured

```bash
python main_redact.py --dataset_name  /fsx/leandro/data/pii_result/$LANG --target_dataset $LANG-no-pii --save_path_disk $LANG-no-pii-local
```