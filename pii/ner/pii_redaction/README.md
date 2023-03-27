# PII redaction

```bash
LANG=python
python main_redact.py --dataset_name  /fsx/leandro/data/pii_result/$LANG --target_dataset $LANG-no-pii --save_path_disk $LANG-no-pii-local
```