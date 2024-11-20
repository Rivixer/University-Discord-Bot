# pylint: disable=all

import json
from pathlib import Path
from typing import TYPE_CHECKING, Generator

import pytest
from pytest import MonkeyPatch

from university_bot.cogs.role_assignment import (
    RoleAssignment,
    RoleAssignmentController,
    RoleAssignmentEmbedModel,
    RoleAssignmentModel,
    ServerRole,
)

from .mocks import *

if TYPE_CHECKING:
    from nextcord.interactions import Interaction


TEST_JSON_PATH = Path("test_assigning_roles.json")


@pytest.fixture
def model(monkeypatch: MonkeyPatch) -> Generator[RoleAssignmentModel, None, None]:
    data = {
        "roles": {
            "group_0": {"role_id": 123, "description": "Role number 1", "emoji": "1️⃣"},
            "guest": {"role_id": 345, "description": "Guest role", "emoji": "*️⃣"},
        }
    }
    with open(TEST_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)
    monkeypatch.setattr(RoleAssignmentModel, "_settings_path", TEST_JSON_PATH)
    yield RoleAssignmentModel("test")
    TEST_JSON_PATH.unlink()


@pytest.fixture
def embed_model(model: RoleAssignmentModel) -> RoleAssignmentEmbedModel:
    return RoleAssignmentEmbedModel(model, BotMock(GuildMock()))  # type: ignore


@pytest.fixture
def ctrl(
    model: RoleAssignmentModel, embed_model: RoleAssignmentEmbedModel
) -> RoleAssignmentController:
    return RoleAssignmentController(model, embed_model)


@pytest.fixture
def default_groups() -> list[ServerRole]:
    return [
        ServerRole(123, "Role number 1", "1️⃣"),
        ServerRole(345, "Guest role", "*️⃣"),
    ]


def _add_group_to_json(name: str, role_id: int, desc: str, emoji: str) -> None:
    with open(TEST_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["roles"][name] = {"role_id": role_id, "description": desc, "emoji": emoji}
    with open(TEST_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)


@pytest.mark.asyncio
async def test_validate_indentifier() -> None:
    class Cog:
        _controllers = {"test": None}

    @RoleAssignment._validate_identifier
    async def command(cog, _, identifier: str) -> None:
        pass

    interaction: Interaction = None  # type: ignore
    await command(Cog(), interaction, "test")
    with pytest.raises(ValueError):
        await command(Cog(), interaction, "not_existsing_group")


def test_group_info() -> None:
    group = ServerRole(123, "testing group", "1️⃣")
    assert group.info == "1️⃣ - testing group"


def test_load_not_existsing_group(model: RoleAssignmentModel) -> None:
    with pytest.raises(KeyError):
        model._load_role("not_existsing_group")


def test_load_groups(model: RoleAssignmentModel) -> None:
    _add_group_to_json("group_1", 345, "desc3", "3️⃣")
    model.reload_settings()


def test_groups_data(model: RoleAssignmentModel) -> None:
    expected = {
        "group_0": {"role_id": 123, "description": "Role number 1", "emoji": "1️⃣"},
        "guest": {"role_id": 345, "description": "Guest role", "emoji": "*️⃣"},
    }

    assert model._roles_data == expected
    open(TEST_JSON_PATH, "w", encoding="utf-8").write("{}")
    with pytest.raises(TypeError):
        model.reload_settings()


@pytest.mark.asyncio
async def test_change_group_role(ctrl: RoleAssignmentController) -> None:
    group_0_role = RoleMock("group_0", 123, 0x111111)
    guest_role = RoleMock("guest", 345, 0x222222)

    group_0_partial_emoji = PartialEmojiMock("1️⃣")
    guest_partial_emoji = PartialEmojiMock("*️⃣")
    invalid_partial_emoji = PartialEmojiMock("📣")

    guild = GuildMock()
    guild.roles = [group_0_role, guest_role]

    member = MemberMock(
        name="TestName",
        nick="TestNick",
        global_name="TestGlobalName",
        discriminator="1234",
        id=1234567890,
        roles=[group_0_role],
        _guild=guild,
    )

    # Change group_0 to guest
    await ctrl.change_role(guest_partial_emoji, member)  # type: ignore
    assert member.roles == [guest_role]

    # Change guest to group_0
    await ctrl.change_role(group_0_partial_emoji, member)  # type: ignore
    assert member.roles == [group_0_role]

    # Try to change group_0 using invalid emoji
    with pytest.raises(AttributeError):
        await ctrl.change_role(invalid_partial_emoji, member)  # type: ignore


def test_embed_reaction(embed_model: RoleAssignmentEmbedModel) -> None:
    assert embed_model.reactions == ["1️⃣", "*️⃣"]
