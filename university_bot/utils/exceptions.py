# SPDX-License-Identifier: MIT
"""A module for utility functions and classes related to exceptions."""

__all__ = ("format_exception_chain",)


def format_exception_chain(error: Exception, *, sep: str = " -> ") -> str:
    """Formats the full chain of exceptions into a single string.

    Parameters
    ----------
    error: :class:`Exception`
        The exception to format.
    sep: :class:`str`
        The separator to use between exceptions.

    Returns
    -------
    :class:`str`
        The formatted exception chain.

    Examples
    --------
    Formatting a single exception:
    ```
    try:
        raise ValueError("An error occurred")
    except ValueError as e:
        msg = format_exception_chain(e)
        print(msg)  # ValueError: An error occurred
    ```
    Formatting a chained exception:
    ```
    def foo():
        raise ValueError("Initial error")
    def bar():
        try:
            foo()
        except ValueError as e:
            raise TypeError("Another error") from e
    try:
        bar()
    except TypeError as e:
        msg = format_exception_chain(e)
        print(msg)  # TypeError: Another error -> ValueError: Initial error
        msg = format_exception_chain(e, sep=" | "))
        print(msg)  # TypeError: Another error | ValueError: Initial error
    ```
    """

    messages: list[str] = []
    current_error = error

    while current_error:
        messages.append(f"{type(current_error).__name__}: {current_error}")
        current_error = current_error.__cause__ or current_error.__context__

    return sep.join(messages)
