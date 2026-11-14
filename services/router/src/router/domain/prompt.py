import re

USER_MESSAGE_OPEN = "<user_message>"
USER_MESSAGE_CLOSE = "</user_message>"
_ZWSP = "​"
_TAG_RE = re.compile(r"<\s*/?\s*user_message\s*/?\s*>", re.IGNORECASE)


def build_user_prompt(body: str) -> str:
    """Wrap user-supplied text in a tagged block and neutralise inner wrappers.

    The body may itself contain variants of `<user_message>` / `</user_message>`
    (different case, inner whitespace). We insert a zero-width space right after
    the opening `<` so the sequence no longer parses as a tag, which stops
    attempts to break out of the enclosing block.
    """
    neutralised = _TAG_RE.sub(lambda m: "<" + _ZWSP + m.group(0)[1:], body)
    return f"{USER_MESSAGE_OPEN}\n{neutralised}\n{USER_MESSAGE_CLOSE}"
