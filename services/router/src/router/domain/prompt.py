USER_MESSAGE_OPEN = "<user_message>"
USER_MESSAGE_CLOSE = "</user_message>"
_ZWSP = "​"


def build_user_prompt(body: str) -> str:
    """Wrap user-supplied text in a tagged block and neutralise inner wrappers.

    The body may itself contain `<user_message>` / `</user_message>`; we insert a
    zero-width space inside those tags so the model keeps seeing exactly one
    enclosing block and cannot be tricked into a prompt-injection breakout.
    """
    neutralised = body.replace(USER_MESSAGE_CLOSE, f"</user_message{_ZWSP}>").replace(
        USER_MESSAGE_OPEN, f"<user_message{_ZWSP}>"
    )
    return f"{USER_MESSAGE_OPEN}\n{neutralised}\n{USER_MESSAGE_CLOSE}"
