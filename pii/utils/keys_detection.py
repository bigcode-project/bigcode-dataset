import os
import tempfile

from detect_secrets import SecretsCollection
from detect_secrets.settings import transient_settings
from gibberish_detector import detector

# Secrets detection with detect-secrets tool


filters = [
    # some filters from [original list](https://github.com/Yelp/detect-secrets/blob/master/docs/filters.md#built-in-filters)
    # were removed based on their targets
    {"path": "detect_secrets.filters.heuristic.is_potential_uuid"},
    {"path": "detect_secrets.filters.heuristic.is_likely_id_string"},
    {"path": "detect_secrets.filters.heuristic.is_templated_secret"},
    {"path": "detect_secrets.filters.heuristic.is_sequential_string"},
]
plugins = [
    {"name": "ArtifactoryDetector"},
    {"name": "AWSKeyDetector"},
    # the entropy detectors esp Base64 need the gibberish detector on top
    {"name": "Base64HighEntropyString"},
    {"name": "HexHighEntropyString"},
    {"name": "AzureStorageKeyDetector"},
    {"name": "CloudantDetector"},
    {"name": "DiscordBotTokenDetector"},
    {"name": "GitHubTokenDetector"},
    {"name": "IbmCloudIamDetector"},
    {"name": "IbmCosHmacDetector"},
    {"name": "JwtTokenDetector"},
    {"name": "MailchimpDetector"},
    {"name": "NpmDetector"},
    {"name": "SendGridDetector"},
    {"name": "SlackDetector"},
    {"name": "SoftlayerDetector"},
    {"name": "StripeDetector"},
    {"name": "TwilioKeyDetector"},
    # remove 3 plugins for keyword
    # {'name': 'BasicAuthDetector'},
    # {'name': 'KeywordDetector'},
    # {'name': 'PrivateKeyDetector'},
]


def is_gibberish(matched_str):
    """Checks to make sure the PII span is gibberish and not word like"""
    # pip install gibberish-detector
    # download the training corpora from https://raw.githubusercontent.com/domanchi/gibberish-detector/master/examples/big.txt
    # run gibberish-detector train big.txt > big.model to generate the model (it takes 3 seconds)
    Detector = detector.create_from_model('gibberish_data/big.model')
    return Detector.is_gibberish(matched_str.lower())


def is_hash(content, value):
    """Second check if the value is a hash (after gibberish detector)"""
    # get the line where value occurred
    try:
        res = content.index(value)
    except ValueError:
        # TODO: fix this issue happened one for JS in the stack-smol, file did contain value
        print("Value not found in content, why this happened?")
        return False
    lines = content[:content.index(value)].splitlines()
    target_line = lines[-1]
    if len(value) in [32, 40, 64]:
        # if "sha" or "md5" are in content:
        keywords = ["sha", "md5", "hash", "byte"]
        if any(x in target_line.lower() for x in keywords):
            return True
    return False

def file_has_hashes(content, coeff = 0.02):
    """Checks if the file contains literals 'hash' or 'sha' for more than 2% nb_of_lines"""
    lines = content.splitlines()
    count_sha = 0
    count_hash = 0
    nlines = content.count("\n")
    threshold = int(coeff * nlines)
    for line in lines:
        count_sha += line.lower().count("sha")
        count_hash += line.lower().count("hash")
        if count_sha > threshold or count_hash > threshold:
            return True
    return False

def get_indexes(text, value):
    string = text
    indexes = []
    new_start = 0
    while True:
        try:
            start = string.index(value)
            indexes.append(new_start + start)
            new_start = new_start + start + len(value)
            string = text[new_start:]
        except ValueError:
            break
    indexes = [(x, x + len(value)) for x in indexes]
    return indexes


def detect_keys(content, suffix=".txt"):
    """Detect secret keys in content using detect-secrets tool
    Args:
        content (str): string containing the text to be analyzed.
        suffix (str): suffix of the file
    Returns:
        A list of dicts containing the tag type, the matched string, and the start and
        end indices of the match."""

    fp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False, mode="w")
    fp.write(content)
    fp.close()
    secrets = SecretsCollection()
    with transient_settings(
        {"plugins_used": plugins, "filters_used": filters}
    ) as settings:
        secrets.scan_file(fp.name)
    os.unlink(fp.name)
    secrets_set = list(secrets.data.values())
    matches = []
    if secrets_set:
        for secret in secrets_set[0]:
            if not is_gibberish(secret.secret_value):
                continue
            if is_hash(content, secret.secret_value) or file_has_hashes(content):
                continue
            indexes = get_indexes(content, secret.secret_value)
            for start, end in indexes:
                matches.append(
                    {
                        "tag": "KEY",
                        "value": secret.secret_value,
                        "start": start,
                        "end": end,
                    }
                )
    return matches



