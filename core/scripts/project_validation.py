"""This project's own check of a reviewer's final report. PROJECT-OWNED: the sync never replaces it.

The review adapters (claude_bridge.py, codex_bridge.py) are kit-owned and every sync replaces
them, so a check the project adds there is lost (#87). They call validate_final_message() on
each reviewer's final report when this file sits beside them or in the scripts/ of the
repository they review (the Codex plugin's bundled adapters). Delete the file and nothing more
is checked.
"""


def validate_final_message(text: str) -> str | None:
    """Return None when the final report passes, or a short reason when it does not.

    `text` is the reviewer's final report: Codex's final message, or Claude's verdict, findings
    and manual checks, one per line. A reason fails the review as invalid_evidence:<reason>
    and its verdict is not used; the reason is shown on one line, cut at 200 characters. An
    exception raised here, or a sys.exit(), fails the review too.
    """
    # Example, from a project whose invalid reports held letters of a non-Latin alphabet (#87):
    #   import re
    #   if re.search(r"[^\W\d_A-Za-zÀ-ɏ]", text):
    #       return "the final report holds non-Latin letters"
    return None
