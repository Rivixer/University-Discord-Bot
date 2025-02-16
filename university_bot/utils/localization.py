# SPDX-License-Identifier: MIT
"""A module that provides localization support.

This module provides localization support for commands and responses.
It allows for the retrieval of localized strings for commands, parameters,
and choices based on the user's locale.

Attributes
----------
Localization: :class:`.Localization`
    A class providing localization support.
"""

from __future__ import annotations

import inspect
import json
import string
from typing import TYPE_CHECKING, Any, ClassVar, overload

from nextcord import Locale, SlashOption

from university_bot.utils.logger import get_logger

if TYPE_CHECKING:
    from nextcord import SlashApplicationCommand, SlashApplicationSubcommand

    from university_bot import Interaction
    from university_bot.config import LocalizationConfig


__all__ = (
    "Localization",
    "LocalizationGroup",
    "LocalizedGroup",
)

_logger = get_logger(__name__)


def _resolve_key(data: dict[str, Any], keys: list[str], default: Any) -> Any:
    result = data
    for key in keys:
        result = result.get(key)
        if result is None:
            return default
    return result


class Localization:
    """A class providing localization support."""

    _config: LocalizationConfig
    _data: dict[Locale, dict[str, Any]] = {}
    _loaded: bool = False

    _def_locale: ClassVar[Locale] = Locale.en_US

    @staticmethod
    def default_locale() -> Locale:
        """Returns the default locale."""
        return Localization._def_locale

    @classmethod
    def load(cls, config: LocalizationConfig) -> None:
        """Loads the localization data.

        Parameters
        ----------
        config: :class:`.LocalizationConfig`
            The localization configuration.
        """
        cls._config = config

        # Cause global _logger doesn't work here, idk why
        logger = get_logger(__name__)
        logger.info(
            "Loading localization data. Enabled locales: %s.",
            config.enabled_locales,
        )

        supported_locales = [l.name for l in Locale]
        unsupported_locales = [
            i.stem
            for i in config.directory.glob("*.json")
            if i.stem not in supported_locales
        ]

        if any(unsupported_locales):
            logger.warning("Unsupported locales: %s.", unsupported_locales)
            logger.warning("Supported locales: %s.", supported_locales)

        for file in config.directory.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    if file.stem in config.enabled_locales:
                        locale = Locale(file.stem)
                        cls._data[locale] = json.load(f)
            except json.JSONDecodeError as e:
                _logger.error("Failed to decode JSON file %s. %s", file, e)
            except OSError as e:
                _logger.error("Failed to open file %s. %s", file, e)
            else:
                logger.debug("Loaded localization data for %s.", file.stem)

        if missing_locales := set(config.enabled_locales) - set(cls._data.keys()):
            logger.warning(
                "Missing localization data for locales: %s.", list(missing_locales)
            )

        cls._loaded = True

    @classmethod
    def get_group(cls, key: str) -> LocalizationGroup:
        """Returns a localization group for a specific key.

        This method retrieves a localization group for a specific key.
        The group contains localized values for the key across all supported locales.

        Parameters
        ----------
        key: :class:`str`
            The key for the localization group.

        Returns
        -------
        :class:`.LocalizationGroup`
            The localization group containing localized values for the key.
        """
        groups: dict[Locale, dict[str, Any]] = {}
        keys = key.split(".")
        for locale, locale_data in cls._data.items():
            groups[locale] = _resolve_key(locale_data, keys, {})
        return LocalizationGroup(groups)

    @classmethod
    def get_localized_choice_name(
        cls,
        interaction: Interaction,
        param_name: str,
        choice_key: str,
    ) -> str:
        """Returns a localized name for a specific choice in a command parameter.

        This function retrieves the translated name of a choice option from the localization data.
        If no translation is found, it returns the original choice key.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The Discord interaction from which the locale and command data will be retrieved.
        param_name: :class:`str`
            The name of the command parameter for which the choice is being retrieved.
        choice_key: :class:`str`
            The original choice key that needs localization.

        Returns
        -------
        :class:`str`
            The localized name of the choice, or the original
            `choice_key` if no translation is available.

        Example
        -------
        ```python
        status = Localization.get_localized_choice_name(interaction, "status", "online")
        print(status)  # Output (in Polish locale): "dostępny"
        ```
        """

        if not cls._loaded:
            _logger.warning("Localization not loaded. Returning default choice key.")
            return choice_key

        locale = Locale(interaction.locale)
        data = cls._data.get(locale, {}).get("commands", {})

        interaction_data: dict[str, Any] = interaction.data  # type: ignore
        for command in cls._extract_command_path(interaction_data):
            data = data.get(f"/{command}", {})

        return (
            data.get("#params", {})
            .get(param_name, {})
            .get("choices", {})
            .get(choice_key, choice_key)
        )

    @staticmethod
    def _safe_format(_text_: str, **kwargs: Any):
        formatter = string.Formatter()
        result = ""
        for literal_text, field_name, format_spec, _ in formatter.parse(_text_):
            result += literal_text
            if field_name is not None:
                try:
                    value = formatter.get_field(field_name, [], kwargs)[0]
                    result += format(value, format_spec or "")
                except (AttributeError, KeyError, ValueError):
                    result += "{" + field_name + "}"
        return result

    @classmethod
    def get_command_response(
        cls,
        interaction: Interaction,
        key: str,
        default: str,
        **kwargs: Any,
    ) -> str:
        """Retrieves a localized response content for a given command and key.

        This method looks up the localized response string for a command
        based on the interaction's locale. If no translation is found
        at the command's specific level, it will progressively search higher
        levels in the command tree until a matching response is found.
        If no localization is available at any level, the provided
        default value is returned.

        Parameters
        ----------
        interaction: :class:`nextcord.Interaction`
            The interaction from which the locale and command data will be retrieved.
        key: :class:`str`
            The key for the response message."
        default: :class:`str`
            The default message to use if no translation is found.
        **kwargs: `Any`
            Additional parameters to format the response string.

        Returns
        -------
        :class:`str`
            The localized response message content,
            formatted with the given keyword arguments.

        Raises
        ------
        ValueError
            If the keyword `_text_` is used in `kwargs`, as it is reserved.

        Notes
        -----
        - The localization data must be loaded before using this decorator.
        - If the key is not found at the command level, the function will recursively
            check higher levels in the command tree. This allows for generic responses
            to be defined at parent command levels.
        - Placeholders inside responses `{}` will be replaced
            using provided keyword arguments.


        Example
        -------
        ```python
        content = Localization.get_command_response(
            interaction,
            "congrats",
            "{user.mention} Congratulations!",
            user=interaction.user,
        )
        ```
        """

        if not cls._loaded:
            _logger.warning("Localization not loaded. Returning default value.")
            return default

        if "_text_" in kwargs:
            raise ValueError(
                "'_text_' is a reserved keyword and cannot be used as a key in kwargs."
            )

        locale = Locale(interaction.locale)
        data = cls._data.get(locale, {}).get("commands", {})

        interaction_data: dict[str, Any] = interaction.data  # type: ignore
        command_path = cls._extract_command_path(interaction_data)

        response = cls._find_response(data, command_path, key, default)
        return cls._safe_format(response, **kwargs)

    @staticmethod
    def _extract_command_path(interaction_data: dict[str, Any]) -> list[str]:
        """Extracts the full command path from interaction data."""
        command_path = [interaction_data["name"]]

        while "options" in interaction_data and interaction_data["options"]:
            option = interaction_data["options"][0]
            if option.get("type") == 1:  # Subcommand
                command_path.append(option["name"])
                interaction_data = option
            else:
                break

        return command_path

    @staticmethod
    def _find_response(
        data: dict[str, Any], command_path: list[str], key: str, default: str
    ) -> str:
        for i in range(len(command_path), 0, -1):
            current_data = data
            for name in command_path[:i]:
                current_data = current_data.get(f"/{name}", {})

            if "#responses" in current_data and key in current_data["#responses"]:
                return current_data["#responses"][key]

        return default

    @overload
    @staticmethod
    def apply_localizations(component: SlashApplicationCommand) -> Any:
        """Automatically applies localized names, descriptions,
        and parameter localizations to a slash command.

        This decorator retrieves translations from the :class:`.Localization`
        and assigns them to `name_localizations` and `description_localizations`
        for the command and its parameters.

        It must be placed **above** the `@nextcord.slash_command` decorator.

        Parameters
        ----------
        component: `nextcord.SlashApplicationCommand`
            The slash command to which localizations should be applied.

        Notes
        -----
        - The localization data must be loaded before using this decorator.
        - Missing localizations will be replaced with default values specified in the command.
        - Localizations for parameters (SlashOption) are also applied,
            including names, descriptions, and choices.

        Example
        -------
        ```python
        @Localization.apply_localizations
        @nextcord.slash_command(name="command", description="A test command.")
        async def _command(
            interaction: Interaction,
            option: str = SlashOption(name="option", description="An option"),
        ) -> None:
            ...
        ```

        In this example:
        - The command's name and description will be localized (if available).
        - The `option` parameter will also receive localized name and description (if available).
        - If localizations are missing, provided default values will be used.
        """

    @overload
    @staticmethod
    def apply_localizations(component: SlashApplicationSubcommand) -> Any:
        """Automatically applies localized names, descriptions,
        and parameter localizations to a slash subcommand.

        This decorator retrieves translations from the :class:`.Localization`
        and assigns them to `name_localizations` and `description_localizations`
        for the subcommand and its parameters.

        It must be placed **above** the `@subcommand` decorator.

        Parameters
        ----------
        component: `nextcord.SlashApplicationSubcommand`
            The slash subcommand to which localizations should be applied.

        Notes
        -----
        - The localization data must be loaded before using this decorator.
        - Missing localizations will be replaced with default values specified in the subcommand.
        - Localizations for parameters (SlashOption) are also applied,
            including names, descriptions, and choices.

        Example
        -------
        ```python
        @nextcord.slash_command(name="command", description="Placeholder for a command group.")
        async def _command(_: Interaction) -> None:
            ...

        @Localization.apply_localizations
        @_command.subcommand(name="subcommand", description="A test subcommand.")
        async def _subcommand(
            interaction: Interaction,
            option: str = SlashOption(name="option", description="An option"),
        ) -> None:
            ...
        ```

        In this example:
        - The subcommand's name and description will be localized (if available).
        - The `option` parameter will also receive localized name and description (if available).
        - If localizations are missing, provided default values will be used.
        """

    @staticmethod
    def apply_localizations(
        component: SlashApplicationCommand | SlashApplicationSubcommand,
    ) -> Any:
        """apply_localizations"""
        if not Localization._loaded:
            _logger.warning(
                "Localization not loaded. Applying localizations will have no effect. (%s)",
                component.qualified_name,
            )
            return component

        name_localizations = {}
        description_localizations = {}

        for locale, data in Localization._data.items():
            command_data = Localization._get_command_data(
                component.qualified_name, data
            )
            if "name" in command_data:
                name_localizations[locale] = command_data["name"]
            if "description" in command_data:
                description_localizations[locale] = command_data["description"]

        component.name_localizations = name_localizations
        component.description_localizations = description_localizations
        sig = inspect.signature(component.callback)  # type: ignore

        for param_name, param in sig.parameters.items():
            if not isinstance(param.default, SlashOption):
                continue

            option = param.default
            param_translations = Localization._get_param_translations(
                component.qualified_name, param_name, param.default.name
            )

            # Build a dictionary of all public, non-callable attributes from the option.
            # Skip attributes that raise ValueError.
            option_vars = {}
            for attr in dir(option):
                if attr.startswith("_"):
                    continue
                try:
                    attr_value = getattr(option, attr)
                except ValueError:
                    continue
                if not callable(attr_value):
                    option_vars[attr] = attr_value

            # Format each localized translation using option_vars.
            for translations in param_translations.copy().values():
                if option.default is not None:
                    for locale, translation in translations.items():
                        if not isinstance(translation, str):
                            continue
                        translations[locale] = Localization._safe_format(
                            translation, **option_vars
                        )
            # Assign the processed localization dictionaries to the option's attributes.
            option.name_localizations = param_translations.get("name", {})
            option.description_localizations = param_translations.get("description", {})
            option.choice_localizations = param_translations.get("choices", {})

        return component

    @staticmethod
    def _get_command_data(command_name: str, data: dict[str, Any]) -> dict[str, Any]:
        command_data = data.get("commands", {})
        for name in command_name.split():
            command_data = command_data.get(f"/{name}", {})
        return command_data

    @staticmethod
    def _get_param_translations(
        command_name: str,
        param_name: str,
        param_slash_name: str | None,
    ) -> dict[str, Any]:
        translations: dict[str, Any] = {"name": {}, "description": {}, "choices": {}}

        for locale, data in Localization._data.items():
            command_data = Localization._get_command_data(command_name, data)
            params_data: dict[str, Any] = command_data.get("#params", {})
            param_data = (
                param_slash_name
                and params_data.get(param_slash_name, None)
                or params_data.get(param_name, {})
            )

            if "name" in param_data:
                translations["name"][locale] = param_data["name"]
            if "description" in param_data:
                translations["description"][locale] = param_data["description"]
            if "choices" in param_data:
                for key, value in param_data["choices"].items():
                    if key not in translations["choices"]:
                        translations["choices"][key] = {}
                    translations["choices"][key][locale] = value

        return translations


class LocalizationGroup:
    """Represents a group of localized values for a specific key.

    This class stores localized values for various locales in a nested
    dictionary structure. Each locale maps to its own dictionary
    containing keys and associated values. It provides methods to retrieve
    localized values for a given locale or to extract a subset (group)
    of the localization data.
    """

    _data: dict[Locale, dict[str, Any]] = {}

    def __init__(self, data: dict[Locale, dict[str, Any]]) -> None:
        self._data = data

    def get[T](self, locale: Locale, key: str, default: T = None) -> T:
        """Retrieves a localized value for a specific locale.

        This method navigates the nested dictionary for the given locale
        using a dot-separated key. If the key is not found, the provided
        default value is returned.

        Parameters
        ----------
        locale: :class:`nextcord.Locale`
            The locale for which the value should be retrieved.
        key: :class:`str`
            The key for the localized value.
        default: `T` | `None`
            The default value to return if the key is not found.

        Returns
        -------
        `T` | `None`
            The localized value for the key in the specified locale.
        """
        keys = key.split(".")
        data = self._data.get(locale, {})
        return _resolve_key(data, keys, default)

    def get_group(self, key: str) -> LocalizationGroup:
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
        groups: dict[Locale, dict[str, Any]] = {}
        keys = key.split(".")
        for locale, locale_data in self._data.items():
            groups[locale] = _resolve_key(locale_data, keys, {})
        return LocalizationGroup(groups)


class LocalizedGroup:
    """Represents a group of localized values for a specific key.

    This class providing a simplified interface for retrieving localized values
    and nested groups without having to specify the locale each time.
    """

    _loc: LocalizationGroup
    __locale: Locale

    def __init__(self, locale: Locale, loc: LocalizationGroup) -> None:
        self._loc = loc
        self.__locale = locale

    def get(self, key: str, default: str = "") -> str:
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

    def get_group(self, key: str) -> LocalizedGroup:
        """Retrieves a nested localized group for a specific key.

        This method returns a new LocalizedGroup instance representing
        a subset of the localized data for the stored locale, based
        on the provided dot-separated key.


        Parameters
        ----------
        key: :class:`str`
            The key for the nested localized group.

        Returns
        -------
        :class:`.LocalizedGroup`
            The nested localized group containing localized values for the key.
        """
        return LocalizedGroup(self.__locale, self._loc.get_group(key))
