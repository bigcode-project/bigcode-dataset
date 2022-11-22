import json
import random
import string
import ipaddress


# List of random private IP addresses to use as replacements
REPLACEMENTS_IP = {
    "IPv4": ["172.16.31.10", "172.16.58.3", "172.16.17.32", "192.168.127.12", "192.168.3.11"],
    "IPv6": [
        "fd00:c2b6:b24b:be67:2827:688d:e6a1:6a3b",
        "fd00:a516:7c1b:17cd:6d81:2137:bd2a:2c5b",
        "fc00:e968:6179::de52:7100",
        "fc00:db20:35b:7399::5",
        "fdf8:f53e:61e4::18",
    ],
}

# providergs = ["google", "cloudfare", "alternate-dns", "quad9","open-dns", "comodo", "adguard"]
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


def load_json(sample):
    try:
        return json.loads(sample)
    except ValueError:
        return []


def random_replacements(n=10):
    """Build dictionaries of random replacements for PII (key, email, IP address)

    Emails: replace with one of n [random string of 5 characters + @example.com]
    IP addresses: replace with one of n synthetic private IP addresses (IPv4 or IPv6)
    Keys: replace with one of n [sequence of 32 random characters/digits]

    TODO: add IPv6 and IPv4 separation
    """
    letters = string.ascii_lowercase
    lettters_digits = string.ascii_lowercase + string.digits
    emails = [
        "".join(random.choice(letters) for i in range(5)) + "@example.com"
        for i in range(n)
    ]
    keys = [
        "".join(random.choice(lettters_digits) for i in range(32)) for i in range(n)
    ]
    ip_addresses = REPLACEMENTS_IP
    return {"EMAIL": emails, "KEY": keys, "IP_ADDRESS": ip_addresses}


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


def is_private_ip(ip):
    """Check if an IP address is allocated for private networks"""
    ip = ipaddress.ip_address(ip)
    return ip.is_private


def redact_pii_text(text, secrets, replacements, add_references=False):
    """Redact PII in a text
    Args:
        text (str): text to redact
        secrets (json): json string with the secrets to redact
        replacements (dict): dictionary of replacements for each PII type
        add_references (bool): whether to add references to the redacted text (delimiters to PII)
        for vizualization
    Returns:
        text (str): new text with redacted secrets
    """
    secrets = load_json(secrets)
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
            # skip secret if it's an IP address for private networks or popular DNS servers
            if secret["tag"] == "IP_ADDRESS":
                # if secret value in popular DNS servers, skip it
                if is_private_ip(secret["value"]) or (secret["value"] in POPULAR_DNS_SERVERS):
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
    result = (new_text, references, modified) if add_references else (new_text, modified)
    return result


def redact_pii_batch(examples, replacements, add_references=True):
    """Anonymize PII in a batch of examples from a dataset"""
    new_contents = []
    references = []
    modified = []
    for text, secrets, has_secrets in zip(
        examples["content"],
        examples["secrets"],
        examples["has_secrets"],
    ):
        if has_secrets:
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
