# PII redaction
<<<<<<< HEAD
To run PII redaction on a dataset that went though PII detection with StarPII using the code in `./pii_inference` folder:
```bash
mkdir  ./logs
LANG=python
python main_redact.py --dataset_name  $DATA_PATH --target_dataset $LANG-no-pii --save_path_disk $LANG-no-pii-local
```

To run multiple `slurm` jobs for each programming language

```bash
python run_pii_slurm.py --start 0 --end 88
```
