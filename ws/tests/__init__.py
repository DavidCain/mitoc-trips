import re

WHITESPACE = re.compile(r"[\n\s]+")


def strip_whitespace(text):
    return re.sub(WHITESPACE, " ", text).strip()
