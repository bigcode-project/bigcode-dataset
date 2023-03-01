import re
from collections import OrderedDict

import datasets
import regex
import torch
from transformers import pipeline

# regexes used for removing automated text
GITHUB_EMAILS = [
    re.compile(pattern, re.DOTALL)
    for pattern in [
        "(.*)From:.+Reply to this email directly.+view it on GitHub(.*)\n?(.*)",
        "(.*)On.+notifications@github.com.+wrote:.+Reply to this email directly.+view it on GitHub(.*)\n?(.*)",
        "(.*)Signed-off-by: .+<.+>(.*?)\n?(.*)",
    ]
]
GITHUB_EMAIL_DATE = re.compile("\d+/\d+/\d+ \d{2}:\d{2} [AP]M.+wrote")
GITHUB_EMAIL_LINEBREAK = re.compile("_{20,}")

# we remove comments from authors in this list
BOT_AUTHORS = [
    "Apache-HBase",
    "AutorestCI",
    "CLAassistant",
    "cmsbuild",
    "codecov-io",
    "codecov-commenter",
    "coveralls",
    "danger-public",
    "dnfclas",
    "msftclas",
    "PyDocTeur",
    "SparkQA",
    "karma-pr-reporter",
    "danger-public",
    "claassistantio",
    "probot-stale",
]
# we remove comments if author username contains a keyword in this list
BOT_KEYWORDS = ["[bot]", "botmanager", "bors-", "jenkins", "k8s-", "-test-", "travis"]

# we remove comments if author username ends with a suffix in this list
BOT_SUFFIXES = [
    "-automaton",
    "-automation",
    "-benchmark",
    "-build",
    "-deployer",
    "-cloud",
    "bot",
    "-ci",
    "-linter",
    "-teamcity",
    "-test",
    "-testing",
    "-Service-Account",
]


def merge_text_columns(example):
    """Combines description and comment to one column (text)

    Descriptions are issue-level text (body of text when opening an issue),
    comments are replies to the parent issue or one of its comments.
    We merge them as an event cannot have both at the same time.
    """
    events_new = []
    text_columns = ["comment", "description"]
    for event_old in example["events"]:
        event_new = {k: v for k, v in event_old.items() if k not in text_columns}
        comment, description = event_old["comment"], event_old["description"]
        text = comment if comment else description
        event_new["text"] = text if text else ""
        events_new.append(event_new)
    example["events"] = events_new
    return example


def _strip_automated_email_text(text):
    """Removes text auto-generated when users post in issues via email reply"""
    if text:
        text = text.strip()
    else:
        return ""
    # try to extract with regex directly
    for pattern in GITHUB_EMAILS:
        m = pattern.match(text)
        if m:
            break
    if m:
        text = m.group(1) + m.group(3)
    else:
        # if no exact matches, apply matching line by line and
        # get potential content before/after automated email text
        lines = text.split("\n")
        start, end = 0, -1
        for i, line in enumerate(lines):
            line = line.strip()
            if "notifications@github.com" in line or bool(
                GITHUB_EMAIL_DATE.search(line)
            ):
                start = i
            if "Reply to this email directly" in line:
                end = i + 1 if line.endswith(":") else i
            if line.startswith(">"):
                # remove quoted text in replies
                end = i
        text = "\n".join(lines[:start] + lines[end + 1 :])
    # remove page break line
    return GITHUB_EMAIL_LINEBREAK.sub("", text).strip()


def strip_automated_email_text(example):
    """Removes auto-generated text from emails in Github issues"""
    # assumes merge_text_columns() was already applied on dataset
    example["events"] = [
        {
            k: _strip_automated_email_text(v) if k == "text" else v
            for k, v in event.items()
        }
        for event in example["events"]
    ]
    return example


def truncate_long_comments(example, max_lines=80):
    """Truncates long comments in the middle (we keep teh last 20 lnes)"""
    for event in example["events"]:
        lines = event["text"].split("\n")
        nb_lines = len(lines)
        if nb_lines > max_lines:
            event["text"] = "\n".join(lines[: max_lines - 20]) + "\n[Truncated]\n"
            event["text"] += "\n".join(lines[-20:])
    return example


def remove_bot_comments(example):
    """Discard auto comments from issues based on author pattern matching"""
    filtered_events = []
    modified = False
    last_removed = 0
    for i, event in enumerate(example["events"]):
        author = event["author"]
        # assumes single `text' field rather than comment/description
        is_bot = (
            any(bp.lower() in author.lower() for bp in BOT_KEYWORDS)
            or any(author.lower().endswith(s) for s in BOT_SUFFIXES)
            or any(author == a for a in BOT_AUTHORS)
        )
        if not is_bot:
            filtered_events.append(event)
        else:
            if i > 0 and last_removed > 0 and last_removed < i - 1:
                # if previous message was not removed, check if it was a bot call
                previous_comment = example["events"][i - 1]["text"]
                is_bot_call = author in previous_comment or previous_comment.startswith(
                    "/"
                )
                if is_bot_call:
                    filtered_events.pop()
                    bot_calls["calls"].append(previous_comment)
                    nb_calls += 1
            last_removed = i
            modified = True
    example["events"] = filtered_events
    example["bot_issue"] = len(example["events"]) == 0
    example["modified_by_bot"] = modified
    return example


def filter_based_users_size(example, minimum=200, maximum=7000, max_events=10):
    """We filter out short files and those with only one user, except if the size
    of text in comments is between minimum and maximum characters
    and issue has less than max_events events.
    """
    if example["text_size"] < minimum:
        return False
    if example["user_count"] >= 2:
        return True
    else:
        if example["text_size"] <= maximum and example["event_count"] <= max_events:
            return True
        return False


def replace_usernames(example):
    """Replaces real usernames (from authors list) with placeholders in GitHub issues"""
    example["modified_usernames"] = False
    usernames = [event["author"] for event in example["events"]]
    usernames = {
        u: f"username_{i}" for i, u in enumerate(OrderedDict.fromkeys(usernames))
    }
    for event in example["events"]:
        event["masked_author"] = usernames[event["author"]]
        for u_old, u_new in usernames.items():
            if u_old in event["text"]:
                example["modified_usernames"] = True
                event["text"] = event["text"].replace(u_old, u_new)
    return example
