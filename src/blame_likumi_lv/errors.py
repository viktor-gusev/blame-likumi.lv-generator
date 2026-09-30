class BlameLikumiError(Exception):
    """Base error for expected pipeline failures."""


class UnknownStructureError(BlameLikumiError):
    """Likumi.lv returned a page whose expected structure was not found."""


class VerificationError(BlameLikumiError):
    """Generated output does not match the official normalized snapshot."""

