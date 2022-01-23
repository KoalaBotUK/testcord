__all__ = (
    'TestcordException'
)


class TestcordException(Exception):
    """Base exception class for testcord

    Ideally speaking, this could be caught to handle any exceptions raised from this library.
    """

    pass


class TestOperationNotImplemented(TestcordException):
    """Exception that's raised when a method from pycord is unsuccessful due to operation
    not being implemented within testcord yet.
    """
    def __init__(self, operation):
        super().__init__(f"{operation} is not yet supported by Testcord, please request this feature on our GitHub")
