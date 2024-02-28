# Fine-tuning StarEncoder on an NER task  for PII detection

To run the training on an annotated PII dataset (`bigcode/pii-full-ds` in our case, you might need to adapt the code to fit your dataset), use the following command: 
```bash
python -m torch.distributed.launch \
        --nproc_per_node number_of_gpus train.py \
        --dataset_name bigcode/pii-full-ds \
        --debug \
        --learning_rate 2e-5 \
        --train_batch_size 8 \
        --bf16 \
        --add_not_curated
```
Note that we use a global batch size of 64 (8*8 GPUs). To use only curated dataset remove the flag `--add_not_curated`.