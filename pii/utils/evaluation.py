import json

TAGS = ['EMAIL', 'IP_ADDRESS', 'KEY']


def load_json(sample):
    try:
        return json.loads(sample)
    except ValueError:
        return []


def overlapped(a, b, alpha=0.8, beta=0.8):
    """Returns True if the intervals a and b overlap for more than 80% of their lengths"""
    size_overlap = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    ref_overlap = size_overlap / (b[1] - b[0])
    pred_overlap = size_overlap / (a[1] - a[0])
    return (ref_overlap > alpha and pred_overlap > beta)


def compare_intervals(references, predictions, alpha=0.8, beta=0.8):
    """Compare two lists of intervals and return the number 
    of true positives, false positives and false negatives.
    >>> compare_intervals([(0, 7), (10, 20)], [(1,8), (99, 119)], 0, 0)[0]
    {'TP': 1, 'FN': 1, 'FP': 1}
    """
    ref_intervals = sorted(references, key=lambda x: x[0])
    pred_intervals = sorted(predictions, key=lambda x: x[0])
    scores = {"TP": 0, "FN": 0, "FP": 0}
    detected_secrets = []
    for interval in pred_intervals:
        for target in ref_intervals:
            if overlapped(interval, target, alpha, beta):
                # the prediction is a true positive
                scores["TP"] += 1
                detected_secrets.append(interval)
                break
        else:
            # the prediction is a false positive
            scores["FP"] += 1
    # the rest of the targets that aren't detected are false negatives
    scores["FN"] += len(ref_intervals) - len(detected_secrets)
    return scores, detected_secrets


def recall_precision(metrics_dict):
    """Compute recall and precision for each tag"""
    metrics = {}
    for tag in TAGS:
        metrics[tag] = {}
        total = metrics_dict[tag]['TP'] + metrics_dict[tag]['FN'] + metrics_dict[tag]['FP']
        if total:
            if not (metrics_dict[tag]['TP'] + metrics_dict[tag]['FN']) or not (metrics_dict[tag]['TP'] + metrics_dict[tag]['FP']):
                # handle division by zero
                metrics[tag] = {'recall': 0, 'precision': 0}
            else:
                metrics[tag]['recall'] = metrics_dict[tag]['TP'] / (metrics_dict[tag]['TP'] + metrics_dict[tag]['FN'])
                metrics[tag]['precision'] = metrics_dict[tag]['TP'] / (metrics_dict[tag]['TP'] + metrics_dict[tag]['FP'])
        else:
            # if there are no annotations, the score is 1
            metrics[tag] = {'recall': 1.0, 'precision': 1.0}
    return metrics


def recall_precision_all_tags(metrics_dict):
    """Compute recall and precision for all tags"""
    metrics = {}
    TP = sum([metrics_dict[tag]['TP'] for tag in TAGS])
    FN = sum([metrics_dict[tag]['FN'] for tag in TAGS])
    FP = sum([metrics_dict[tag]['FP'] for tag in TAGS])
    if not (TP + FN) or not (TP + FP):
        metrics = {'recall': 0, 'precision': 0}
    else:
        metrics['recall'] = TP / (TP + FN)
        metrics['precision'] = TP / (TP + FP)
    return metrics


def evaluate_pii(references, predictions, alpha=0.8, beta=0.8):
    """Evaluate predictions of PII against references"""
    metrics_dict = {}
    for tag in TAGS:
        ref_intervals = [(e['start'], e['end']) for e in references if e['tag'] == tag]
        pred_intervals = [(e['start'], e['end']) for e in predictions if e['tag'] == tag]
        metrics, _ = compare_intervals(ref_intervals, pred_intervals, alpha, beta)
        metrics_dict[tag] = metrics
    return metrics_dict


def evaluate_pii_ds(dataset, pred_column='pii', ref_column="secrets", overall_score=False, alpha=0.8, beta=0.8):
    """Evaluate predictions of PII against references in a dataset
    """
    metrics_dict = {tag: {'TP': 0, 'FN': 0, 'FP': 0} for tag in TAGS}
    for i in range(len(dataset)):
        ref_list = load_json(dataset[i][ref_column])
        pred_list = load_json(dataset[i][pred_column])
        sample_metrics = evaluate_pii(ref_list, pred_list, alpha, beta)
        for tag in TAGS:
            for metric in metrics_dict[tag]:
                metrics_dict[tag][metric] += sample_metrics[tag][metric]
    if overall_score:
        return recall_precision_all_tags(metrics_dict), metrics_dict
    return recall_precision(metrics_dict), metrics_dict