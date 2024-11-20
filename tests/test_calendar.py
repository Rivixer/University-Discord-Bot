# pylint: disable=all

import datetime
import functools
import json
import uuid
from pathlib import Path
from typing import Any, Generator

import pytest
from nextcord.ui import TextInput
from pytest import MonkeyPatch

from university_bot.cogs.calendar import (
    CalendarController,
    CalendarEmbedModel,
    CalendarModel,
    Event,
    EventModal,
    EventModalType,
    Reminder,
    ReminderModal,
)

from .mocks import *

TEST_JSON_PATH = Path("test_calendar.json")


@pytest.fixture
def model(monkeypatch: MonkeyPatch) -> Generator[CalendarModel, None, None]:
    open(TEST_JSON_PATH, "w", encoding="utf-8").write("{}")
    monkeypatch.setattr(CalendarModel, "_settings_path", TEST_JSON_PATH)
    yield CalendarModel()
    TEST_JSON_PATH.unlink()


@pytest.fixture
def ctrl(model: CalendarModel) -> CalendarController:
    embed_model = CalendarEmbedModel(model, BotMock(GuildMock()))  # type: ignore
    return CalendarController(model, embed_model)


@pytest.fixture
def datetime_now() -> datetime.datetime:
    return datetime.datetime.now().replace(microsecond=0)


@pytest.fixture
def date_now(datetime_now: datetime.datetime) -> datetime.date:
    return datetime_now.date()


@pytest.fixture
def time_now(datetime_now: datetime.datetime) -> datetime.time:
    return datetime_now.time().replace(second=0)


def _load_data_from_json() -> dict[str, Any]:
    with open(TEST_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_add_event_to_json(model: CalendarModel) -> None:
    dt = datetime.datetime(2012, 12, 2, 14, 15)
    event = Event("TestDescription", dt.date(), dt.time(), "TestPrefix", "TestLocation")
    model.add_event_to_json(event)
    file_data = _load_data_from_json()
    assert file_data.get("events") == {
        event.uuid: {
            "description": "TestDescription",
            "date": "02.12.2012",
            "time": "14.15",
            "prefix": "TestPrefix",
            "location": "TestLocation",
            "is_hidden": False,
            "reminder": None,
        }
    }


def test_add_hidden_event_to_json(model: CalendarModel) -> None:
    dt = datetime.datetime(2012, 12, 2, 14, 15)
    event = Event(
        "TestDescription", dt.date(), dt.time(), "TestPrefix", "TestLocation", True
    )
    model.add_event_to_json(event)
    file_data = _load_data_from_json()
    assert file_data.get("events") == {
        event.uuid: {
            "description": "TestDescription",
            "date": "02.12.2012",
            "time": "14.15",
            "prefix": "TestPrefix",
            "location": "TestLocation",
            "is_hidden": True,
            "reminder": None,
        }
    }


@pytest.mark.parametrize(
    "date_str", ["1.11.2023", "1:11:2023", "1-11-2023", "1/11/2023"]
)
@pytest.mark.parametrize("time_str", ["11.22", "11:22", "11-22", "11/22"])
def test_add_event_with_datetime_separated_by_various_formats(
    ctrl: CalendarController, date_str: str, time_str: str
):
    event = ctrl.add_event_from_input("", date_str, time_str, "", "")
    expected_datetime = datetime.datetime(2023, 11, 1, 11, 22)
    expected_date = expected_datetime.date()
    expected_time = expected_datetime.time()
    assert event.date == expected_date
    assert event.time == expected_time
    assert ctrl.model.events_data[event.uuid]["date"] == "01.11.2023"
    assert ctrl.model.events_data[event.uuid]["time"] == "11.22"


def test_add_event_with_invalid_date(ctrl: CalendarController) -> None:
    with pytest.raises(ValueError):
        ctrl.add_event_from_input("", "30.02.2022", None, "", "")


def test_add_event_with_invalid_time(ctrl: CalendarController) -> None:
    with pytest.raises(ValueError):
        ctrl.add_event_from_input("", "01.02.2022", "25:33", "", "")


def test_add_event_by_command(ctrl: CalendarController) -> None:
    event = ctrl.add_event_from_input(
        "TestDescription", "1.11:2023", "11-22", "TestPrefix", "TestLocation"
    )
    dt = datetime.datetime(2023, 11, 1, 11, 22)
    assert event.description == "TestDescription"
    assert event.date == dt.date()
    assert event.time == dt.time()
    assert event.prefix == "TestPrefix"
    assert event.location == "TestLocation"
    assert ctrl.model.events_data[event.uuid] == {
        "description": "TestDescription",
        "date": "01.11.2023",
        "time": "11.22",
        "prefix": "TestPrefix",
        "location": "TestLocation",
        "is_hidden": False,
        "reminder": None,
    }


def test_read_event_from_json(model: CalendarModel) -> None:
    dt = datetime.datetime(2023, 2, 23, 1, 0)
    uuid_example = str(uuid.uuid4())
    data = {
        "events": {
            uuid_example: {
                "description": "test",
                "date": "23.02.2023",
                "time": "01.00",
                "prefix": "prefix",
                "location": "location",
                "reminder": None,
            }
        }
    }

    with open(TEST_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)
    model._load_settings()

    event = Event("test", dt.date(), dt.time(), "prefix", "location")
    event._uuid = uuid_example

    assert model.calendar_data == [event]


def test_remove_event_from_json(
    model: CalendarModel, date_now: datetime.date, time_now: datetime.time
) -> None:
    event = Event("test", date_now, time_now, "prefix", "location")
    model.add_event_to_json(event)
    model.remove_event_from_json(model.calendar_data[0])
    assert model.events_data == {}
    assert model.calendar_data == []
    file_data = _load_data_from_json()
    assert file_data.get("events") == {}


def test_is_all_day_event(model: CalendarModel, date_now: datetime.datetime) -> None:
    event = Event("test", date_now, None, "", "")
    model.add_event_to_json(event)
    event = model.calendar_data[0]
    assert event.is_all_day is True
    assert event.date.strftime("%H:%M:%S:%f") == "00:00:00:000000"


def test_sort_calendar_data_with_other_time(model: CalendarModel) -> None:
    dt = datetime.datetime(2024, 12, 12, 22, 0)
    event_now = Event("", dt.date(), dt.time(), "", "")
    model.add_event_to_json(event_now)

    dt_later = dt + datetime.timedelta(minutes=10)
    event_later = Event("", dt_later.date(), dt_later.time(), "", "")
    model.add_event_to_json(event_later)

    dt_earlier = dt - datetime.timedelta(minutes=10)
    event_earlier = Event("", dt_earlier.date(), dt_earlier.time(), "", "")
    model.add_event_to_json(event_earlier)

    assert model.calendar_data == [event_earlier, event_now, event_later]


def test_sort_calendar_data_with_other_day(
    model: CalendarModel, date_now: datetime.date
) -> None:
    event_now = Event("", date_now, None, "", "")
    model.add_event_to_json(event_now)

    earlier = date_now + datetime.timedelta(days=10)
    event_later = Event("", earlier, None, "", "")
    model.add_event_to_json(event_later)

    later = date_now - datetime.timedelta(days=10)
    event_earlier = Event("", later, None, "", "")
    model.add_event_to_json(event_earlier)

    assert model.calendar_data == [event_earlier, event_now, event_later]


def test_sort_calendar_data_all_day_first(
    model: CalendarModel, date_now: datetime.date, time_now: datetime.time
) -> None:
    model.add_event_to_json(event1 := Event("", date_now, None, "", ""))
    model.add_event_to_json(event2 := Event("", date_now, time_now, "", ""))
    model.add_event_to_json(event3 := Event("", date_now, None, "", ""))
    assert model.calendar_data == [event1, event3, event2]


def test_get_grouped_events(model: CalendarModel) -> None:
    dt = datetime.datetime(2025, 5, 3, 10, 20)
    dt_next_day = dt + datetime.timedelta(days=1)

    model.add_event_to_json(event1 := Event("", dt.date(), None, "", ""))
    model.add_event_to_json(event2 := Event("", dt_next_day.date(), None, "", ""))
    model.add_event_to_json(event3 := Event("", dt.date(), dt.time(), "", ""))
    model.add_event_to_json(
        event4 := Event("", dt_next_day.date(), dt_next_day.time(), "", "")
    )
    expected = [
        (dt.date(), [event1, event3]),
        (dt_next_day.date(), [event2, event4]),
    ]
    assert list(model.get_grouped_events()) == expected


@pytest.mark.parametrize(
    "test_name, datetime, is_all_day, expected_result",
    [
        (
            "not_all_day__true",
            datetime.datetime.now() - datetime.timedelta(minutes=10),
            False,
            True,
        ),
        (
            "all_day__true",
            (datetime.datetime.now() - datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=0
            ),
            True,
            True,
        ),
        (
            "not_all_day__false",
            datetime.datetime.now() + datetime.timedelta(minutes=10),
            False,
            False,
        ),
        (
            "all_day__false",
            (datetime.datetime.now() + datetime.timedelta(days=1)).replace(
                hour=0, minute=0, second=0
            ),
            True,
            False,
        ),
        (
            "all_day__the_same_day__false",
            datetime.datetime.now().replace(hour=0, minute=0, second=0),
            True,
            False,
        ),
    ],
)
def test_event_expired(
    test_name: str,
    datetime: datetime.datetime,
    is_all_day: bool,
    expected_result: bool,
):
    time = datetime.time() if not is_all_day else None
    event = Event("", datetime.date(), time, "", "")
    assert event.is_expired == expected_result


def test_remove_expired_event(
    model: CalendarModel,
    datetime_now: datetime.datetime,
) -> None:
    datetime_now = datetime_now.replace(second=0)

    dt_earlier = datetime_now - datetime.timedelta(minutes=10)
    expired_event__not_all_day = Event("", dt_earlier.date(), dt_earlier.time(), "", "")
    model.add_event_to_json(expired_event__not_all_day)

    dt_previous_day = datetime_now - datetime.timedelta(days=1)
    expired_event__all_day = Event("", dt_previous_day.date(), None, "", "")
    model.add_event_to_json(expired_event__all_day)

    dt_later = datetime_now + datetime.timedelta(minutes=10)
    not_expired_event__not_all_day = Event("", dt_later.date(), dt_later.time(), "", "")
    model.add_event_to_json(not_expired_event__not_all_day)

    dt_next_day = datetime_now + datetime.timedelta(days=1)
    not_expired_event__all_day = Event("", dt_next_day.date(), None, "", "")
    model.add_event_to_json(not_expired_event__all_day)

    removed_events = model.remove_expired_events()
    assert removed_events == [
        expired_event__all_day,
        expired_event__not_all_day,
    ]
    assert model.calendar_data == sorted(
        [
            not_expired_event__all_day,
            not_expired_event__not_all_day,
        ],
        key=functools.cmp_to_key(Event.compare_method),
    )


event_full_name_and_info_data = [
    ("test", datetime.datetime(2023, 1, 23, 9, 34), "", "", False, "**test** (9:34)"),
    ("test", datetime.datetime(2023, 1, 23, 0, 0), "", "", True, "**test**"),
    ("test", datetime.datetime(2023, 1, 23, 0, 0), "", "", False, "**test** (0:00)"),
    (
        "test",
        datetime.datetime(2023, 1, 23, 0, 0),
        "prefix",
        "",
        True,
        "[prefix] **test**",
    ),
    (
        "test",
        datetime.datetime(2023, 1, 23, 0, 0),
        "",
        "location",
        True,
        "**test** [location]",
    ),
    (
        "test",
        datetime.datetime(2023, 1, 23, 0, 0),
        "prefix",
        "location",
        True,
        "[prefix] **test** [location]",
    ),
    (
        "test",
        datetime.datetime(2023, 1, 23, 14, 5),
        "prefix",
        "location",
        False,
        "[prefix] **test** [location] (14:05)",
    ),
]


@pytest.mark.parametrize(
    "name, datetime, prefix, location, all_day, expected_full_name",
    event_full_name_and_info_data,
)
def test_event_full_name(
    name: str,
    datetime: datetime.datetime,
    prefix: str,
    location: str,
    all_day: bool,
    expected_full_name: str,
):
    time = datetime.time() if not all_day else None
    event = Event(name, datetime.date(), time, prefix, location)
    assert event.full_name == expected_full_name


@pytest.mark.parametrize(
    "name, datetime, prefix, location, all_day, expected_full_info",
    event_full_name_and_info_data,
)
def test_event_full_info(
    name: str,
    datetime: datetime.datetime,
    prefix: str,
    location: str,
    all_day: bool,
    expected_full_info: str,
):
    time = datetime.time() if not all_day else None
    event = Event(name, datetime.date(), time, prefix, location)
    assert event.full_info == f"(23.01.2023) {expected_full_info}"


def test_event_weekday() -> None:
    monday = datetime.datetime(2023, 2, 27)
    event = Event("test1", monday, None, "", "")
    assert event.weekday == "poniedziałek"


def test_get_event_from_empty_calendar(model: CalendarModel) -> None:
    with pytest.raises(IndexError):
        model.get_event_at_index(0)


def test_get_event_with_index_zero_from_non_empty_calendar(
    model: CalendarModel,
    date_now: datetime.date,
    time_now: datetime.time,
) -> None:
    event = Event("", date_now, time_now, "", "")
    model.add_event_to_json(event)
    with pytest.raises(IndexError):
        model.get_event_at_index(0)


def test_get_event_with_index_greater_than_list_size(
    model: CalendarModel,
    date_now: datetime.date,
    time_now: datetime.time,
) -> None:
    event = Event("", date_now, time_now, "", "")
    model.add_event_to_json(event)
    with pytest.raises(IndexError):
        model.get_event_at_index(2)


def test_get_event_from_non_empty_calendar(
    model: CalendarModel,
    date_now: datetime.date,
    time_now: datetime.time,
) -> None:
    event = Event("", date_now, time_now, "", "")
    model.add_event_to_json(event)
    received_event = model.get_event_at_index(1)
    assert event == received_event


def test_remove_event(
    model: CalendarModel,
    date_now: datetime.date,
    time_now: datetime.time,
) -> None:
    event = Event("", date_now, time_now, "", "")
    model.add_event_to_json(event)
    model.remove_event_from_json(event)
    assert model.calendar_data == []


@pytest.mark.asyncio
async def test_add_event_in_the_past(ctrl: CalendarController) -> None:
    modal = EventModal(EventModalType.ADD, controller=ctrl)
    with pytest.raises(ValueError):
        modal._validate_datetime("01.01.2000", "00:00")


@pytest.mark.asyncio
async def test_add_event_in_the_far_future(ctrl: CalendarController) -> None:
    modal = EventModal(EventModalType.ADD, controller=ctrl)
    with pytest.raises(ValueError):
        modal._validate_datetime("01.01.9999", "00:00")


@pytest.mark.asyncio
async def test_add_event_in_the_same_day_in_the_past(
    ctrl: CalendarController,
    datetime_now: datetime.datetime,
) -> None:
    if datetime_now.time().hour == 0 and datetime_now.time().minute == 0:
        pytest.skip("Test cannot be run at 00:00")
    modal = EventModal(EventModalType.ADD, controller=ctrl)
    with pytest.raises(ValueError):
        modal._validate_datetime(datetime_now.date().strftime("%d.%m.%Y"), "00:00")


@pytest.mark.asyncio
async def test_add_event_in_the_same_day_in_the_future(
    ctrl: CalendarController,
    datetime_now: datetime.datetime,
) -> None:
    if datetime_now.time().hour == 23 and datetime_now.time().minute == 59:
        pytest.skip("Test cannot be run at 23:59")
    modal = EventModal(EventModalType.ADD, controller=ctrl)
    modal._validate_datetime(datetime_now.date().strftime("%d.%m.%Y"), "23:59")


@pytest.mark.asyncio
async def test_add_event_in_the_same_day_all_day(
    ctrl: CalendarController,
    datetime_now: datetime.datetime,
) -> None:
    modal = EventModal(EventModalType.ADD, controller=ctrl)
    modal._validate_datetime(datetime_now.date().strftime("%d.%m.%Y"), None)


def test_add_event_with_now_date_and_time(
    datetime_now: datetime.datetime,
) -> None:
    with pytest.raises(ValueError):
        EventModal._validate_datetime(
            None,  # type: ignore
            datetime_now.date().strftime("%d.%m.%Y"),
            datetime_now.time().strftime("%H:%M"),
        )


def test_add_reminder_to_event(ctrl: CalendarController) -> None:
    event = ctrl.add_event_from_input("", "01.01.2023", "00:00", "", "")
    reminder = Reminder("2023-01-01T00:00:00", "content", "", 123, [456], {})
    event.reminder = reminder
    assert ctrl.model.events_data[event.uuid]["reminder"] == reminder.to_dict()


def test_remove_reminder_from_event(ctrl: CalendarController) -> None:
    event = ctrl.add_event_from_input("", "01.01.2023", "00:00", "", "")
    reminder = Reminder("2023-01-01 00:00:00", "content", "", 123, [456], {})
    event.reminder = reminder
    event.reminder = None
    assert ctrl.model.events_data[event.uuid]["reminder"] is None


@pytest.mark.asyncio
async def test_add_reminder_to_event_with_invalid_date(
    ctrl: CalendarController,
) -> None:
    event = ctrl.add_event_from_input("", "01.01.2023", "00:00", "", "")
    dt = datetime.datetime(2022, 1, 1, 0, 0)
    modal = ReminderModal(event, GuildMock())  # type: ignore
    with pytest.raises(ValueError):
        modal._validate_datetime(dt)


def test_reminder_to_dict() -> None:
    reminder = Reminder("2023-01-01T00:00:00", "content", "", 123, [456], {})
    assert reminder.to_dict() == {
        "datetime_iso": "2023-01-01T00:00:00",
        "content": "content",
        "more_info": "",
        "channel_id": 123,
        "role_ids": [456],
        "sent_data": {},
    }
