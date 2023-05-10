## Run NER inference
Here we provide the code used for training [StarPII](https://huggingface.co/bigcode/starpii) and NER model for PII detection.  We also provide the code (and `slurm` scripts) used for running Inference on [StarCoderData](https://huggingface.co/datasets/bigcode/starcoderdata), we were able to detect PII in ~800GB of text in 800 GPU hours on A100 80GB.
```
accelerate config
accelerate launch ner_inference.py --process_batch_size=100000 --out_path=processed_dataset
```
To replace secrets in StarCoderData we used teh following tokens:
<NAME>, <EMAIL>, <KEY>, <PASSWORD>
To mask IP addresses, we randomly selected an IP address from 5~synthetic, private, non-internet-facing IP addresses of the same type.