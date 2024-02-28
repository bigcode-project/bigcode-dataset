import ipaddress
import random
from gibberish_detector import detector

IGNORE = ["AMBIGUOUS", "USERNAME"]
# List of random private IP addresses to use as replacements
REPLACEMENTS_IP = {
    "IPv4": [
        "172.16.31.10",
        "172.16.58.3",
        "172.16.17.32",
        "192.168.127.12",
        "192.168.3.11",
    ],
    "IPv6": [
        "fd00:c2b6:b24b:be67:2827:688d:e6a1:6a3b",
        "fd00:a516:7c1b:17cd:6d81:2137:bd2a:2c5b",
        "fc00:e968:6179::de52:7100",
        "fc00:db20:35b:7399::5",
        "fdf8:f53e:61e4::18",
    ],
}

# DNS to avoid masking
POPULAR_DNS_SERVERS = [
    "8.8.8.8",
    "8.8.4.4",
    "1.1.1.1",
    "1.0.0.1",
    "76.76.19.19",
    "76.223.122.150",
    "9.9.9.9",
    "149.112.112.112",
    "208.67.222.222",
    "208.67.220.220",
    "8.26.56.26",
    "8.20.247.20",
    "94.140.14.14",
    "94.140.15.15",
]


def is_key(matched_str):
    """Checks to make sure the PII span is long enough and is gibberish and not word like"""
    # pip install gibberish-detector
    # download the training corpora from https://raw.githubusercontent.com/domanchi/gibberish-detector/master/examples/big.txt
    # run gibberish-detector train big.txt > big.model to generate the model (it takes 3 seconds)
    Detector = detector.create_from_model(
        "/bigcode-dataset/pii/gibberish_data/big.model"
    )
    is_gibberish = Detector.is_gibberish(matched_str.lower())
    return is_gibberish and len(matched_str) > 8


def is_secret(matched_str):
    """Checks to make sure the PII span is long enough"""
    return len(matched_str) > 3


def is_full_name(matched_str):
    """Checks if detected name is a full names and not just first or last name"""
    return len(matched_str.split()) > 1


def get_replacements():
    """Build dictionaries of replacements for PII (key, email, IP address, name, password)"""
    ip_addresses = REPLACEMENTS_IP
    return {
        "EMAIL": ["<EMAIL>"],
        "KEY": ["<KEY>"],
        "NAME": ["<NAME>"],
        "PASSWORD": ["<PASSWORD>"],
        "IP_ADDRESS": ip_addresses,
    }


def replace_ip(value, replacements_dict):
    """Replace an IP address with a synthetic IP address of the same format"""
    try:
        ipaddress.IPv4Address(value)
        return random.choice(replacements_dict["IP_ADDRESS"]["IPv4"])
    except ValueError:
        try:
            ipaddress.IPv6Address(value)
            return random.choice(replacements_dict["IP_ADDRESS"]["IPv6"])
        except ValueError:
            # this doesn't happen if we already use ipaddress filter in the detection
            print("Invalid IP address")
            return value


def is_secret_ip(ip):
    """Check if an IP address is allocated for private networks (non internet facing), or is not an ip address at all"""
    try:
        ip = ipaddress.ip_address(ip)
    except ValueError:
        # not an ip address
        return True
    return ip.is_private


def redact_pii_text(text, secrets, replacements, add_references=False):
    """Redact PII in a text
    Args:
        text (str): text to redact
        secrets (list): list with the secrets to redact
        replacements (dict): dictionary of replacements for each PII type
        add_references (bool): whether to add references to the redacted text (delimiters to PII)
        for visualization
    Returns:
        text (str): new text with redacted secrets
    """
    modified = False
    if secrets:
        secrets = sorted(secrets, key=lambda x: x["start"])
        # store the secrets that were replaced here with their replacements
        replaced_secrets = {}
        subparts = []
        references = []
        step = 0
        last_text = text
        for secret in secrets:
            # some post-processing 
            if secret["tag"] in IGNORE or not is_secret(secret["value"]):
                continue
            if secret["tag"] == "IP_ADDRESS":
                # skip if it's not actual ip address, is a popular DNS server or private IP address
                if is_secret_ip(secret["value"]) or (
                    secret["value"] in POPULAR_DNS_SERVERS
                ):
                    continue
            if secret["tag"] == "KEY" and not is_key(secret["value"]):
                continue
            if secret["tag"] == "NAME" and not is_full_name(secret["value"]):
                continue
            modified = True
            subtext = text[step : secret["start"]]
            subpart = subtext if subtext else " "
            subparts.append(subpart)
            # if secret is already in replaced_secrets, use the same replacement
            if secret["value"] in replaced_secrets:
                replacement = replaced_secrets[secret["value"]]
            else:
                if secret["tag"] == "IP_ADDRESS":
                    replacement = replace_ip(secret["value"], replacements)
                else:
                    replacement = random.choice(replacements[secret["tag"]])
                replaced_secrets[secret["value"]] = replacement
            subparts.append(replacement)
            replaced_secrets[secret["value"]] = replacement
            if add_references:
                references.append(subpart)
                references.append(f"PI:{secret['tag']}:{replacement}END_PI")
            last_text = text[secret["end"] :]
            step = secret["end"]
        # if supbarpts are not empty join them (it can be empty when all secrets were skipped)
        new_text = "".join(subparts) + last_text if subparts else last_text
        if add_references:
            references = "".join(references) + last_text if references else ""
    else:
        new_text = text
        references = ""
    result = (
        (new_text, references, modified) if add_references else (new_text, modified)
    )
    return result


def redact_pii_batch(examples, replacements, add_references=True):
    """Anonymize PII in a batch of examples from a dataset"""
    new_contents = []
    references = []
    modified = []
    for text, secrets in zip(
        examples["content"],
        examples["entities"],
    ):
        if secrets:
            if add_references:
                new_text, reference, modif = redact_pii_text(
                    text, secrets, replacements, add_references
                )
                references.append(reference)
            else:
                new_text, modif = redact_pii_text(text, secrets, replacements)
            new_contents.append(new_text)
            modified.append(modif)
        else:
            new_contents.append(text)
            references.append(text)
            modified.append(False)
    result = {"new_content": new_contents, "modified": modified}
    if add_references:
        result.update({"references": references})
    return result
