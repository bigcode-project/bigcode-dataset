# source: https://github.com/mponty/bigcode-dataset/tree/main/pii/ner_model_training/utils by @mponty
import numpy as np
from evaluate import load
from scipy.special import softmax
from sklearn.metrics import average_precision_score

_seqeval_metric = load("seqeval")


# NER tags
CATEGORIES = [
    "NAME",
    "NAME_LICENSE",
    "NAME_EXAMPLE",
    "EMAIL",
    "EMAIL_LICENSE",
    "EMAIL_EXAMPLE",
    "USERNAME",
    "USERNAME_LICENSE",
    "USERNAME_EXAMPLE",
    "KEY",
    "IP_ADDRESS",
    "PASSWORD",
]
IGNORE_CLASS = ["AMBIGUOUS", "ID"]

LABEL2ID = {"O": 0}
for cat in CATEGORIES:
    LABEL2ID[f"B-{cat}"] = len(LABEL2ID)
    LABEL2ID[f"I-{cat}"] = len(LABEL2ID)
ID2LABEL = {v: k for k, v in LABEL2ID.items()}


def compute_ap(pred, truth):
    pred_proba = 1 - softmax(pred, axis=-1)[..., 0]
    pred_proba, truth = pred_proba.flatten(), np.array(truth).flatten()
    pred_proba = pred_proba[truth != -100]
    truth = truth[truth != -100]

    return average_precision_score(truth != 0, pred_proba)


def compute_metrics(p):
    predictions, labels = p
    print(f"predictions.shape: {predictions.shape} and type {type(predictions)}")
    print(f"labels.shape: {labels.shape} and type {type(labels)}")
    avg_prec = compute_ap(predictions, labels)
    predictions = np.argmax(predictions, axis=2)

    # Remove ignored index (special tokens)
    true_predictions = [
        [ID2LABEL[p] for (p, l) in zip(prediction, label) if l != -100]
        for prediction, label in zip(predictions, labels)
    ]
    true_labels = [
        [ID2LABEL[l] for (p, l) in zip(prediction, label) if l != -100]
        for prediction, label in zip(predictions, labels)
    ]

    results = _seqeval_metric.compute(
        predictions=true_predictions, references=true_labels
    )
    agg_metrics = {
        "Avg.Precision": avg_prec,
        "precision": results.pop("overall_precision"),
        "recall": results.pop("overall_recall"),
        "f1": results.pop("overall_f1"),
    }
    results.pop("overall_accuracy")
    per_cat_metrics = {name: metrics["f1"] for name, metrics in results.items()}

    return dict(**agg_metrics, **per_cat_metrics)
