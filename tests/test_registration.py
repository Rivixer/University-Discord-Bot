# pylint: disable-all

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import pytest
from nextcord.embeds import Embed
from pytest import MonkeyPatch

from university_bot.cogs.registration import (
    CodeController,
    CodeModel,
    MailLog,
    MemberData,
    RegistrationModel,
)

from .mocks import *

TEST_JSON_PATH = Path("test_registration.json")


@pytest.fixture
def member1() -> MemberMock:
    return MemberMock(
        name="TestName1",
        nick="TestNick1",
        global_name="TestGlobalName1",
        discriminator="1234",
        id=1234567890,
        roles=[
            RoleMock("role1", 123, colour=0x111111),
            RoleMock("role2", 456, colour=0x222222),
        ],
    )


@pytest.fixture
def member2() -> MemberMock:
    return MemberMock(
        name="TestName2",
        nick="TestNick2",
        global_name="TestGlobalName2",
        discriminator="1235",
        id=1234567891,
        roles=[],
    )


def member_data1(monkeypatch: MonkeyPatch, member1: MemberMock) -> MemberData:
    monkeypatch.setattr(MemberData, "__init__", lambda _: None)
    member_data = MemberData()  # type: ignore
    member_data.member = member1  # type: ignore
    member_data.index = "123456"
    member_data.first_name = "First"
    member_data.last_name = "Last"
    member_data.non_student_reason = None
    member_data.other_account_reason = None
    return member_data


class MemberDataMock(MemberData):
    def __init__(
        self,
        member: MemberMock,
        index: str,
        first_name: str,
        last_name: str,
        non_student_reason: str | None = None,
        other_account_reason: str | None = None,
    ) -> None:
        self.member = member  # type: ignore
        self.index = index
        self.first_name = first_name
        self.last_name = last_name
        self.non_student_reason = non_student_reason
        self.other_account_reason = other_account_reason
        self.is_student = non_student_reason is None
        self.other_accounts = []

    def __eq__(self, other: Any) -> bool:
        if not issubclass(type(other), MemberData):
            return False
        return all(
            getattr(self, attr) == getattr(other, attr)
            for attr in ("index", "first_name", "last_name", "non_student_reason")
        )

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "StudentID": self.index,
            "FirstName": self.first_name,
            "LastName": self.last_name,
            "Non-student reason": self.non_student_reason,
            "Another account reason": self.other_account_reason,
        }


def test_member_data_to_embed(member1: MemberMock) -> None:
    guild = GuildMock()
    member1.guild = guild

    member_data = MemberDataMock(
        member1,
        "123456",
        "First",
        "Last",
    )

    embed = member_data.to_embed()
    embed2 = (
        Embed(
            title="User information:",
            description="TestName1#1234 (<@1234567890>)",
            color=0x111111,
        )
        .add_field(
            name="First name",
            value="First",
        )
        .add_field(
            name="Last name",
            value="Last",
        )
        .add_field(name="Student ID", value="123456")
        .add_field(name="ID", value=member1.id, inline=False)
        .add_field(name="Roles", value="<@&456>, <@&123>", inline=False)
        .set_thumbnail(url="link.png")
    )

    assert embed.to_dict() == embed2.to_dict()


def test_matching_members(
    monkeypatch: MonkeyPatch,
    member1: MemberMock,
    member2: MemberMock,
) -> None:
    monkeypatch.setattr(RegistrationModel, "_registered_users_path", TEST_JSON_PATH)

    member1_data = MemberDataMock(
        member1,
        "123456",
        "First",
        "Last",
    )

    member2_data = MemberDataMock(
        member2,
        "123457",
        "First",
        "Last",
    )

    member_data = {
        str(member1.id): member1_data.to_json_dict(),
        str(member2.id): member2_data.to_json_dict(),
    }

    def member_data_init(self: MemberDataMock, member: MemberMock) -> None:
        self.member = member  # type: ignore
        self.index = member_data[str(member.id)]["StudentID"]
        self.first_name = member_data[str(member.id)]["FirstName"]
        self.last_name = member_data[str(member.id)]["LastName"]
        self.non_student_reason = member_data[str(member.id)]["Non-student reason"]
        self.other_account_reason = member_data[str(member.id)][
            "Another account reason"
        ]
        self.is_student = self.non_student_reason is None
        self.other_accounts = []

    monkeypatch.setattr(MemberData, "__init__", member_data_init)
    guild = GuildMock()
    registration_model = RegistrationModel(BotMock(guild))  # type: ignore

    member1.guild = guild
    member2.guild = guild

    result = registration_model.find_matching_members("TestName1")
    assert result == [member1_data]
    result = registration_model.find_matching_members("TestNick2")
    assert result == [member2_data]
    result = registration_model.find_matching_members("123457")
    assert result == [member2_data]
    result = registration_model.find_matching_members("987654")
    assert result == []
    result = registration_model.find_matching_members("asdfasdf")
    assert result == []


def test_mail_log() -> None:
    now = dt.datetime.now()
    mail_log = MailLog("123456", [now])
    assert mail_log.to_dict() == {
        "provided_index": "123456",
        "mails_sent_time": [now.timestamp()],
    }


def test_code_model_valid() -> None:
    model = CodeModel("987654", dt.datetime(2022, 11, 23, 12, 34, 56), [])
    assert model._valid_until == dt.datetime(2022, 11, 23, 20, 34, 56)
    assert model.is_valid is False
    assert model.expire == "23.11.2022 20:34:56"

    model = CodeModel("987654", dt.datetime.now(), [])
    assert model.is_valid is True


def test_code_model_should_send_email() -> None:
    model = CodeModel("xxxxxx", dt.datetime.now(), [])
    assert model.should_send_email("123456") is True

    log1 = MailLog("123456", [dt.datetime.now()])
    log2 = MailLog("987654", [dt.datetime.now() - dt.timedelta(minutes=4)])
    log3 = MailLog("555555", [dt.datetime.now() - dt.timedelta(minutes=20)])

    model.mail_logs = [log1]
    assert model.should_send_email("123456") is False
    assert model.should_send_email("987654") is True

    model.mail_logs = [log1, log2]
    assert model.should_send_email("123456") is False
    assert model.should_send_email("987654") is False

    model.mail_logs = [log1, log2, log3]
    assert model.should_send_email("555555") is True


def test_code_model_check_if_blocked() -> None:
    model = CodeModel("xxxxxx", dt.datetime.now(), [])
    assert model.check_if_blocked("123456") is None

    log1 = MailLog("123456", [dt.datetime.now()])
    log2 = MailLog(
        "234567",
        [
            dt.datetime.now() - dt.timedelta(minutes=20),
            dt.datetime.now() - dt.timedelta(minutes=25),
            dt.datetime.now() - dt.timedelta(minutes=30),
        ],
    )
    log3 = MailLog("345678", [dt.datetime.now() - dt.timedelta(minutes=23)])

    model.mail_logs = [log1]
    assert model.check_if_blocked("123456") is None

    model.mail_logs = [log2]
    assert model.check_if_blocked("234567") is not None

    model.mail_logs = [log1, log2]
    assert model.check_if_blocked("555555") is None

    model.mail_logs = [log1, log2, log3]
    assert model.check_if_blocked("555555") is not None

    model = CodeModel("xxxxxx", dt.datetime.now() - dt.timedelta(hours=9), [])
    model.mail_logs = [log2]
    assert model.check_if_blocked("234567") is None


def test_code_model_add_mail_sent_time() -> None:
    dt_now = dt.datetime.now().replace(microsecond=0)
    model = CodeModel("xxxxxx", dt_now, [])
    model.add_mail_sent_time("123456")
    assert model.mail_logs == [MailLog("123456", [dt_now])]

    model.add_mail_sent_time("123456")
    assert model.mail_logs == [MailLog("123456", [dt_now, dt_now])]


def test_code_model_to_dict() -> None:
    dt_now = dt.datetime.now().replace(microsecond=0)
    log1 = MailLog("123456", [dt_now])
    model = CodeModel("xxxxxx", dt_now, [log1])
    assert model.to_dict() == {
        "code": "xxxxxx",
        "generation_time": dt_now.timestamp(),
        "mail_logs": [log1.to_dict()],
    }


def test_code_controller_generate_code(member1: MemberMock) -> None:
    controller = CodeController("123456", member1)  # type: ignore
    code = controller._generate_code()
    assert len(code) == 8
    assert code.isascii()
