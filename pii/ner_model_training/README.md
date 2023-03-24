Run NER inference

```
accelerate config
accelerate launch ner_inference.py --process_batch_size=100000 --out_path=processed_dataset
```