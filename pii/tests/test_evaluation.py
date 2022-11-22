import json
from utils.evaluation import evaluate_pii_ds

# test evaluation script with a dataset in our format
secrets = [{'tag': 'KEY', 'start': 99, 'end': 110}, {'tag': 'KEY', 'start': 9, 'end': 22}, {'tag': 'EMAIL', 'start': 0, 'end': 7},
           {'tag': 'EMAIL', 'start': 10, 'end': 20}]
pii = [{'tag': 'KEY', 'start': 99, 'end': 112}, {'tag': 'EMAIL', 'start': 1, 'end': 7}, {'tag': 'EMAIL', 'start': 99, 'end': 119}]

dataset = [
    {
        'secrets': json.dumps(secrets),
        'pii': json.dumps(pii),
        
    }
]

def test_evaluation():
    by_tag = evaluate_pii_ds(dataset, overall_score=False, alpha=0.8, beta=0.8)[0]
    overall = evaluate_pii_ds(dataset, overall_score=True, alpha=0.8, beta=0.8)[0]

    assert round(overall['recall'], 2) == 0.5
    assert round(overall['precision'], 2) == 0.67
    assert by_tag == {'EMAIL': {'recall': 0.5, 'precision': 0.5},
                'IP_ADDRESS': {'recall': 1, 'precision': 1},
                'KEY': {'recall': 0.5, 'precision': 1.0}}