# PII detection and Redaction using an NER model
Here we provide code to:
- fine-tune an encoder model (like [StarEncoder](https://huggingface.co/bigcode/starencoder)) for the task of PII detection (NER): see folder `pii_train_ner`
- run inference with our fine-tuned [StarPII](https://huggingface.co/bigcode/starpii) for PII detection on multiple GPUs: see folder `pii_inference`
- redact/mask PII detected with the model: see folder `pii_redaction`

This is the code we used for PII anonymization in the 800GB dataset [StarCoderData](https://huggingface.co/datasets/bigcode/starcoderdata).