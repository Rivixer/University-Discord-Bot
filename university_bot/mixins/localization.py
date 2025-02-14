# SPDX-License-Identifier: MIT
"""A module providing the localization mixin class."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from nextcord import Locale
from nextcord.ui import Button, View

from university_bot.utils.localization import LocalizationGroup, LocalizedGroup

__all__ = (
    "LocalizedMixin",
    "LocalizedViewMixin",
)


class LocalizedMixin:
    """Represents a mixin class for localized views.

    This mixin class provides methods for retrieving localized values
    from a localization group based on the localization group and locale.
    """

    _loc: LocalizationGroup
    __locale: Locale

    def __init__(self, locale: Locale | str | None, loc: LocalizationGroup) -> None:
        self._loc = loc
        locale = locale or "en-US"
        self.__locale = locale if isinstance(locale, Locale) else Locale(locale)

    def get_loc(self, key: str, default: str = "") -> str:
        """Retrieves a localized value for a specific key.

        This method retrieves a localized value for the dot-separated key.
        If the key is not found, the provided default value is returned.

        Parameters
        ----------
        key: :class:`str`
            The key for the localized value.
        default: :class:`str`
            The default value to return if the key is not found.

        Returns
        -------
        :class:`str`
            The localized value for the key.
        """
        return self._loc.get(self.__locale, key, default)

    def get_loc_group(self, key: str) -> LocalizedGroup:
        """Retrieves a nested localization group for a specific key.

        For each locale in the current data, this method extracts
        a nested dictionary based on the provided dot-separated key.
        The result is a new LocalizationGroup containing only that subset.

        Parameters
        ----------
        key: :class:`str`
            The key for the nested localization group.

        Returns
        -------
        :class:`.LocalizationGroup`
            The nested localization group containing localized values for the key.
        """
        return LocalizedGroup(self.__locale, self._loc.get_group(key))


class LocalizedViewMixin(LocalizedMixin):
    """Represents a mixin class for localized views.

    This mixin class provides methods for updating the labels of buttons
    based on the localization group and locale.

    It also provides a decorator to localize the button labels based on the key.

    A class using this mixin should inherit from the `View` class. In addition,
    it should call the `LocalizedViewMixin.__init__` method in its constructor
    AFTER calling the `View.__init__` method.

    Example
    -------
    ```python
    class MyView(LocalizedViewMixin, View):
        def __init__(self, locale: Locale, loc: LocalizationGroup):
            View.__init__(self)
            LocalizedViewMixin.__init__(self, locale, loc)

        @LocalizedViewMixin.localized_button("buttons.my_button")
        @nextcord.ui.button(label="My Button")
        async def my_button(self, button: Button, interaction: Interaction):
            pass
    ```
    """

    def __init__(
        self,
        locale: Locale | str | None,
        loc: LocalizationGroup,
    ) -> None:
        if not issubclass(self.__class__, View):
            raise TypeError("This mixin should be used with the View class.")

        LocalizedMixin.__init__(self, locale, loc)
        self.__update_localized_buttons()

    @dataclass(slots=True, frozen=True)
    class _LocalizedLabel:
        key: str
        default: str

        def __str__(self) -> str:
            return f"{self.__class__.__name__}(key={self.key},default={self.default})"

        @classmethod
        def from_str(cls, value: str) -> LocalizedViewMixin._LocalizedLabel:
            """Creates a new localized label from a string representation.

            Parameters
            ----------
            value: :class:`str`
                The string representation of the localized label.
            """
            pattern = r"^\w+\(key=(?P<key>.*?),default=(?P<default>.*?)\)$"
            match = re.match(pattern, value)
            if not match:
                raise ValueError(f"Invalid string representation: {value}")
            return cls(match.group("key"), match.group("default"))

    @classmethod
    def localized_button(cls, key: str) -> Any:
        """A decorator to localize the button label.

        This decorator localizes the label of the button based on the provided key.
        The key is used to retrieve the localized value from the localization group
        provided in the constructor.

        It should be placed above the `@nextcord.ui.button` decorator, if used.

        If the key is not found, the default button label is used instead.

        Parameters
        ----------
        key: :class:`str`
            The key for the localized value.

        Returns
        -------
        :class:`Any`
            The decorator function.

        Example
        -------
        ```python
            class MyView(LocalizedViewMixin, View):
                @LocalizedViewMixin.localized_button("buttons.my_button")
                @nextcord.ui.button(label="My Button")
                async def my_button(self, button: Button, interaction: Interaction):
                    pass
        ```
        """

        def decorator(func: Any) -> Any:
            func.__discord_ui_model_kwargs__["label"] = str(
                cls._LocalizedLabel(
                    key, func.__discord_ui_model_kwargs__["label"] or key
                )
            )
            return func

        return decorator

    def __update_localized_buttons(self) -> None:
        if (children := getattr(self, "children", None)) is None:
            raise AttributeError(
                "The 'children' attribute is not found. "
                "Did you forget to call the View.__init__ method, "
                "before calling the LocalizedViewMixin.__init__ method?"
            )

        for child in children:  # type: ignore
            if isinstance(child, Button):
                label: str = getattr(child, "label", "")  # type: ignore
                try:
                    localized_label = self._LocalizedLabel.from_str(label)
                except ValueError:
                    continue
                child.label = self.get_loc(localized_label.key, localized_label.default)
