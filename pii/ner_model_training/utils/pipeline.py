from contextlib import contextmanager
from collections import UserDict
from dataclasses import dataclass
from typing import Dict, List, Any, Iterable

import torch
from packaging import version
import numpy as np
from torch.utils.data import DataLoader, IterableDataset
from transformers import is_torch_available, AutoModelForTokenClassification, AutoTokenizer, \
    DataCollatorForTokenClassification
from transformers.utils import ModelOutput

from seqeval.metrics.sequence_labeling import get_entities
from datasets import Dataset

from .chunking import chunk_inputs
from .postprocessing import postprocess


class PiiNERPipeline:
    def __init__(
            self,
            model_name_or_path,
            tokenizer=None,
            device: int = -1,
            window_size=512,
            window_overlap=True,
            batch_size=None,
            num_workers=1,
            id_to_label=None,
            **kwargs,
    ):
        if isinstance(model_name_or_path, str):
            self.model = AutoModelForTokenClassification.from_pretrained(model_name_or_path, **kwargs)
            if tokenizer is None:
                tokenizer = AutoTokenizer.from_pretrained(model_name_or_path, add_prefix_space=True, **kwargs)
            self.tokenizer = tokenizer
        else:
            self.model = model_name_or_path
            self.tokenizer = tokenizer

        if is_torch_available() and isinstance(device, torch.device):
            self.device = device
        else:
            self.device = torch.device("cpu" if device < 0 else f"cuda:{device}")

        self.batch_size = batch_size
        self.num_workers = num_workers
        self.window_size = window_size
        self.window_overlap = window_overlap
        if id_to_label is None:
            self.id_to_label = self.model.config.id2label
        else:
            self.id_to_label = id_to_label

    def __call__(self, inputs: Dataset, **kwargs):
        dataset_iterator = inputs.to_iterable_dataset()
        predict_iterator = self._predict_iterator(inputs, batch_size=self.batch_size)
        for entry, entities in zip(dataset_iterator, predict_iterator):
            yield dict(entities=entities, **entry)

    @contextmanager
    def device_placement(self):
        if torch.cuda.is_available():
            torch.cuda.set_device(self.device)
        yield

    def ensure_tensor_on_device(self, **inputs):
        """
        Ensure PyTorch tensors are on the specified device.

        Args:
            inputs (keyword arguments that should be `torch.Tensor`, the rest is ignored):
                The tensors to place on `self.device`.
            Recursive on lists **only**.

        Return:
            `Dict[str, torch.Tensor]`: The same as `inputs` but on the proper device.
        """
        return self._ensure_tensor_on_device(inputs, self.device)

    def _ensure_tensor_on_device(self, inputs, device):
        if isinstance(inputs, ModelOutput):
            return ModelOutput(
                {name: self._ensure_tensor_on_device(tensor, device) for name, tensor in inputs.items()}
            )
        elif isinstance(inputs, dict):
            return {name: self._ensure_tensor_on_device(tensor, device) for name, tensor in inputs.items()}
        elif isinstance(inputs, UserDict):
            return UserDict({name: self._ensure_tensor_on_device(tensor, device) for name, tensor in inputs.items()})
        elif isinstance(inputs, list):
            return [self._ensure_tensor_on_device(item, device) for item in inputs]
        elif isinstance(inputs, tuple):
            return tuple([self._ensure_tensor_on_device(item, device) for item in inputs])
        elif isinstance(inputs, torch.Tensor):
            if device == torch.device("cpu") and inputs.dtype in {torch.float16, torch.bfloat16}:
                inputs = inputs.float()
            return inputs.to(device)
        else:
            return inputs

    def get_inference_context(self):
        inference_context = (
            torch.inference_mode if version.parse(torch.__version__) >= version.parse("1.9.0") else torch.no_grad
        )
        return inference_context

    def forward(self, model_inputs, **forward_params):
        with self.device_placement():
            inference_context = self.get_inference_context()
            with inference_context():
                model_inputs = self._ensure_tensor_on_device(model_inputs, device=self.device)
                model_outputs = self._forward(model_inputs, **forward_params)
                model_outputs = self._ensure_tensor_on_device(model_outputs, device=torch.device("cpu"))
                model_outputs = {name: tensor.numpy() if isinstance(tensor, torch.Tensor) else tensor
                                 for name, tensor in model_outputs.items()}

        return model_outputs

    def _forward(self, model_inputs, **forward_params):
        # Forward
        input_ids = model_inputs.pop('input_ids')
        logits = self.model(input_ids=input_ids,
                            attention_mask=model_inputs['attention_mask'],
                            return_dict=True,
                            **forward_params)['logits']

        logits = torch.softmax(logits, dim=-1)

        # drop special tokens
        logits, input_ids = logits[:, 1:-1], input_ids[:, 1:-1]

        return {
            "logits": logits,
            "input_ids": input_ids,
            **model_inputs,
        }

    @staticmethod
    def combine_chunks(chunks, offsets, fill_value=0, agg='none'):
        assert agg in ['none', 'average']

        total_length = np.max(offsets) + len(chunks[np.argmax(offsets)])
        total_shape = (total_length, np.shape(chunks[0])[-1])
        combined_chunks = fill_value * np.ones(total_shape, dtype=np.array(chunks[0]).dtype)

        for chunk, offset in zip(chunks, offsets):
            if agg == 'average':
                combined_chunks[offset:offset + len(chunk)] += chunk
            else:
                combined_chunks[offset:offset + len(chunk)] = chunk

        if agg == 'average':
            combined_chunks = combined_chunks / combined_chunks.sum(axis=-1, keepdims=True)

        return combined_chunks

    @staticmethod
    def _get_pipeline_dataloader(dataset, tokenizer, batch_size, num_workers=1, window_size=None, window_overlap=True):
        iterator = PipelineIterator(dataset, tokenizer, window_size=window_size, window_overlap=window_overlap)
        loader = DataLoader(iterator,
                            batch_size=batch_size,
                            num_workers=num_workers,
                            collate_fn=DataCollator(tokenizer))
        return loader

    def _predict_iterator(self, inputs: Dataset, batch_size: int):
        loader = self._get_pipeline_dataloader(inputs, self.tokenizer,
                                               batch_size=batch_size,
                                               window_size=self.window_size,
                                               window_overlap=self.window_overlap,
                                               num_workers=self.num_workers)

        self.model.to(self.device)

        processing_iterator = self.process_inputs(loader)
        for processed in self.combine_chunked_inputs(processing_iterator):
            yield self.extract_entities(text=processed['text'],
                                        logits=processed['logits'],
                                        offset_mapping=processed['offset_mapping'])
        self.model.to('cpu')

    def combine_chunked_inputs(self, processing_iterator):
        for group in self.group_processed_chunks(processing_iterator):
            group['logits'] = self.combine_chunks(group['logits'], group['offset'], agg='average')
            # group['input_ids'] = self.combine_chunks(group['input_ids'], group['offset'],
            #                                          fill_value=self.tokenizer.pad_token_id)
            #
            # mask = group['input_ids'] != self.tokenizer.pad_token_id
            # group['logits'], group['input_ids'] = group['logits'][mask], group['input_ids'][mask]
            yield group

    @staticmethod
    def group_processed_chunks(processing_iterator):
        for group in iterator_group_by(processing_iterator, column='id'):
            text, offset_mapping, idx = group[0]['text'], group[0]['offset_mapping'], group[0]['id']
            group = collate(group)
            group.update(id=idx, text=text, offset_mapping=offset_mapping)
            yield group

    def process_inputs(self, loader):
        for batch in loader:
            outputs = self.forward(batch)
            for sample in uncollate(outputs):
                yield sample

    def extract_entities(self, text, logits, offset_mapping):

        def construct_entity(tag, start, end, score):
            entity = dict(tag=tag,
                          start=start,
                          end=end,
                          value=text[start:end],
                          context=text[max(start - 50, 0):min(end + 50, len(text))],
                          score=score)
            entity = postprocess(entity)
            return entity

        logits = logits[:len(offset_mapping)]

        pred_labels = np.argmax(logits, axis=-1)
        pred_labels = [self.id_to_label[l] for l in pred_labels]
        label_prob = np.max(logits, axis=-1)

        pred_entities = get_entities([pred_labels])

        entities = [construct_entity(
            tag=tag,
            start=offset_mapping[start_idx][0],
            end=offset_mapping[end_idx][-1],
            score=np.mean(label_prob[start_idx:(end_idx + 1)]),
        )
            for tag, start_idx, end_idx in pred_entities]
        return entities


@dataclass
class DataCollator(DataCollatorForTokenClassification):
    _dont_touch = ['text', 'offset', 'id', 'chunk_id', 'offset_mapping']

    def torch_call(self, features):
        keys = [k for k in features[0].keys() if k in self._dont_touch]
        batch = {key: [feature.pop(key) for feature in features] for key in keys}
        batch.update(super().torch_call(features))
        return batch


class PipelineIterator(IterableDataset):
    def __init__(self,
                 dataset,
                 tokenizer,
                 text_column='content',
                 window_size=512,
                 window_overlap=True,
                 ):

        self.dataset = dataset
        self.tokenizer = tokenizer
        self.text_column = text_column
        self.window_overlap = window_overlap
        self.window_size = window_size

    def __len__(self):
        return len(self.dataset)

    def __iter__(self):
        iterator = self.dataset.to_iterable_dataset()
        iterator = iterator.map(lambda x: self.tokenizer.encode_plus(
            x[self.text_column], return_offsets_mapping=True, add_special_tokens=False))

        for item in iterator:
            for chunk in chunk_inputs(
                    **item,
                    tokenizer=self.tokenizer,
                    max_length=self.window_size,
                    overlap_freq=2 if self.window_overlap else 0
            ):
                yield dict(**chunk, text=item[self.text_column], offset_mapping=item['offset_mapping'])


def uncollate(inputs: Dict[str, List[Any]]):
    keys = list(inputs.keys())
    assert all([len(inputs[k]) == len(inputs[keys[0]]) for k in keys]), \
        'All entries must be same length. Inputs lengths: ' + ', '.join([f"{k}: {len(inputs[k])}" for k in keys])
    uncollated = [dict(zip(keys, values)) for values in zip(*[inputs[k] for k in keys])]
    return uncollated


def collate(inputs: List[Dict[str, Any]]):
    keys = inputs[0].keys()
    return {key: [inp[key] for inp in inputs] for key in keys}


def iterator_group_by(iterator: Iterable[Dict[str, Any]], column: str):
    curr_id = None
    grouped_items = []
    for item in iterator:
        if item[column] != curr_id:
            if curr_id is not None:
                yield grouped_items
                grouped_items = []

        curr_id = item[column]
        grouped_items.append(item)

    if len(grouped_items) > 0:
        yield grouped_items
