"""
Redis client and pub/sub management for asynchronous message handling.

This module provides a Redis client manager, a publisher for sending messages,
and a subscriber for listening to channels and dispatching messages to handlers.
It supports publishing and subscribing to Redis channels with protobuf messages,
and includes a mixin for integrating Redis pub/sub functionality into classes.
It also includes a decorator for registering handlers with automatic envelope
deserialization.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import sys
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    Type,
    TypeVar,
    get_type_hints,
    overload,
)

from google.protobuf.message import Message
from redis.asyncio import Redis as _Redis
from redis.asyncio.client import PubSub

if TYPE_CHECKING:
    Redis = _Redis[bytes]
else:
    Redis = _Redis

logger = logging.getLogger(__name__)
_T_Message = TypeVar("_T_Message", bound=Message, contravariant=True)


class RedisManager:
    _redis: ClassVar[Redis | None] = None

    @classmethod
    def initialize(cls, url: str) -> None:
        """Initializes the Redis client.

        If the client is already initialized, it logs a warning and does nothing.

        Parameters
        ----------
        url : str
            The Redis connection URL to connect to.

        Raises
        ------
        redis.ConnectionError
            If the Redis server is unreachable or the connection fails.
        """
        if cls._redis is not None:
            logger.warning("Redis client is already initialized.")
            return

        cls._redis = Redis.from_url(url, decode_responses=False)
        logger.info("Connected to Redis at %s", url)

    @classmethod
    def get_redis(cls) -> Redis:
        """Retrieves the Redis client instance.

        Returns
        -------
        Redis
            The Redis client instance.

        Raises
        ------
        RuntimeError
            If the Redis client has not been initialized.
        """
        if cls._redis is None:
            raise RuntimeError(
                "Redis client is not initialized. Call initialize() first."
            )

        return cls._redis

    @classmethod
    async def close(cls) -> None:
        """|coro|

        Closes the Redis client connection.

        If the client is not initialized, it logs a warning and does nothing.
        """
        if cls._redis is None:
            logger.warning("Redis client is not initialized. Nothing to close.")
            return

        await cls._redis.close()
        cls._redis.connection_pool.disconnect()
        cls._redis = None
        logger.info("Redis connection closed")


class RedisPublisher:
    """Publishes protobuf messages to Redis channels.

    Attributes
    ----------
    channel : str
        The Redis channel to publish messages to.
    """

    __slots__ = ("channel",)

    channel: str

    def __init__(self, channel: str):
        self.channel = channel

    @staticmethod
    async def publish_to_channel(channel: str, /, message: Message) -> None:
        """|coro|

        Publishes a protobuf message to a specified Redis channel.

        Parameters
        ----------
        channel : str
            The Redis channel to publish the message to.
        message : Message
            The protobuf message to publish.
        """
        redis = RedisManager.get_redis()
        data = message.SerializeToString()
        await redis.publish(channel, data)
        logger.debug("Published message to channel %s: %s", channel, message)

    async def publish(self, message: Message) -> None:
        """|coro|

        Publishes a message to this instance's channel.

        Parameters
        ----------
        message : Message
            The protobuf message to publish.
        """
        await self.publish_to_channel(self.channel, message)


class _WaiterEntry(Generic[_T_Message]):
    def __init__(
        self,
        expected_type: Type[_T_Message],
        condition: Callable[[_T_Message], bool],
    ) -> None:
        self.expected_type = expected_type
        self.condition = condition
        self.queue: asyncio.Queue[_T_Message] = asyncio.Queue()


_channel_handlers: dict[str, list[Callable[..., Awaitable[None]]]] = {}


class RedisSubscriber:
    """Subscribes to channels and dispatches incoming protobuf messages to handlers."""

    _pubsub: ClassVar[PubSub | None] = None
    _subscribed: ClassVar[set[str]] = set()
    _waiters: ClassVar[dict[str, list[_WaiterEntry[Any]]]] = defaultdict(list)

    @classmethod
    async def listen(cls) -> None:
        """|coro|

        Listens for messages on registered Redis channels and dispatches them to handlers.

        This method runs indefinitely, listening for new messages on the subscribed channels.
        It deserializes the messages into their respective protobuf envelope classes and
        calls the registered handlers with the deserialized envelope.

        It uses the RedisManager to get the Redis client and subscribe to channels.
        If no channels are registered, it logs a warning and exits.

        Raises
        ------
        RuntimeError
            If the Redis client has not been initialized.
        """

        redis = RedisManager.get_redis()
        cls._pubsub = redis.pubsub()  # type: ignore
        await cls._update_subscriptions()

        async for message in cls._pubsub.listen():
            if message.get("type") != "message":
                continue

            logger.debug("Received message: %s", message)

            raw_channel = message["channel"]
            channel = (
                raw_channel.decode() if isinstance(raw_channel, bytes) else raw_channel
            )
            data = message.get("data")

            handlers = _channel_handlers.get(channel, [])
            waiters = cls._waiters.get(channel, [])

            if not handlers and not waiters:
                logger.warning("Nothing to do for channel %s", channel)
                continue

            if handlers:
                envelope_cls = getattr(handlers[0], "_envelope_cls")
            else:
                envelope_cls = waiters[0].expected_type

            try:
                envelope = envelope_cls()
                envelope.ParseFromString(data)
            except Exception:
                logger.exception("Failed to parse envelope for channel %s", channel)
                continue

            tasks = [asyncio.ensure_future(handler(envelope)) for handler in handlers]

            for entry in waiters:
                if isinstance(envelope, entry.expected_type) and entry.condition(
                    envelope
                ):
                    entry.queue.put_nowait(envelope)

            result = await asyncio.gather(*tasks, return_exceptions=True)

            for res in result:
                if isinstance(res, Exception):
                    logger.exception("Handler raised an exception.")

    @classmethod
    async def _update_subscriptions(cls) -> None:
        if cls._pubsub is None:
            logger.warning(
                "Redis pubsub is not initialized, cannot update subscriptions."
            )
            return

        desired = set(_channel_handlers.keys()) | set(cls._waiters.keys())
        new = desired - cls._subscribed
        gone = cls._subscribed - desired

        if new:
            logger.debug("Subscribing to new channels: %s", new)
            await cls._pubsub.subscribe(*new)  # type: ignore
        if gone:
            logger.debug("Unsubscribing from gone channels: %s", gone)
            await cls._pubsub.unsubscribe(*gone)  # type: ignore

        cls._subscribed = desired

    @overload
    @classmethod
    def subscribe(
        cls,
        channel: str,
        envelope_cls: type[Message],
    ) -> Callable[[Callable[..., Awaitable[None]]], Callable[..., Awaitable[None]]]:
        """Decorator to register a handler for a Redis channel.

        Parameters
        ----------
        channel : str
            The Redis channel to subscribe to.
        envelope_cls : type[Message]
            The protobuf message class to use for deserialization.

        Returns
        -------
        Callable[[Callable[..., Awaitable[None]]], Callable[..., Awaitable[None]]]
            A decorator that registers the function as a handler for the specified channel.

        Raises
        ------
        TypeError
            If the handler function does not accept the specified envelope class or is not a coroutine.

        Examples
        --------
        @RedisSubscriber.subscribe("my_channel", MyEnvelope)
        async def my_handler(envelope) -> None:
            ...
        """

    @overload
    @classmethod
    def subscribe(
        cls, channel: str
    ) -> Callable[[Callable[..., Awaitable[None]]], Callable[..., Awaitable[None]]]:
        """Decorator to register a handler for a Redis channel.

        Parameters
        ----------
        channel : str
            The Redis channel to subscribe to.

        Returns
        -------
        Callable[[Callable[..., Awaitable[None]]], Callable[..., Awaitable[None]]]
            A decorator that registers the function as a handler for the specified channel.

        Raises
        ------
        TypeError
            If the handler function does not accept a protobuf envelope class or is not a coroutine.

        Examples
        --------
        @RedisSubscriber.subscribe("my_channel", MyEnvelope)
        async def my_handler(envelope: MyEnvelope) -> None:
            ...
        """

    @classmethod
    def subscribe(
        cls,
        channel: str,
        envelope_cls: type[Message] | None = None,
    ) -> Callable[[Callable[..., Awaitable[None]]], Callable[..., Awaitable[None]]]:
        def decorator(
            fn: Callable[..., Awaitable[None]],
        ) -> Callable[..., Awaitable[None]]:
            chosen = envelope_cls
            if chosen is None:
                sig = inspect.signature(fn)
                for param in sig.parameters.values():
                    candidate = cls._resolve_annotation(param, fn)
                    if candidate:
                        chosen = candidate
                        break

            if chosen is None:
                raise TypeError(
                    f"Handler {fn.__name__} missing envelope_cls and no protobuf annotation found."
                )

            setattr(fn, "_redis_channel", channel)
            setattr(fn, "_envelope_cls", chosen)

            sig = inspect.signature(fn)
            first = next(iter(sig.parameters.values()), None)
            if first and first.name not in ("self", "cls"):
                if not inspect.iscoroutinefunction(fn):
                    raise TypeError("Handler must be async coroutine.")
                _channel_handlers.setdefault(channel, []).append(fn)
                logger.debug(
                    "Registered handler %s on channel %s", fn.__qualname__, channel
                )
            else:
                logger.debug(
                    "Prepared method handler %s for channel %s",
                    fn.__qualname__,
                    channel,
                )

            return fn

        return decorator

    @staticmethod
    def _resolve_annotation(
        param: inspect.Parameter, fn: Callable[..., Awaitable[None]]
    ) -> type[Message] | None:
        hints = get_type_hints(fn, globalns=fn.__globals__, localns=fn.__globals__)
        ann = hints.get(param.name, inspect.Parameter.empty)
        if inspect.isclass(ann) and issubclass(ann, Message):
            return ann
        raw = param.annotation
        if isinstance(raw, str):
            try:
                module = sys.modules[fn.__module__].__dict__
                resolved = eval(raw, fn.__globals__, module)
                if inspect.isclass(resolved) and issubclass(resolved, Message):
                    return resolved
            except Exception:
                return None
        if inspect.isclass(raw) and issubclass(raw, Message):
            return raw
        return None

    @classmethod
    async def wait_for_event(
        cls,
        channel: str,
        expected_type: Type[_T_Message],
        condition: Callable[[_T_Message], bool],
        timeout: float = 5.0,
    ) -> _T_Message | None:
        # TODO: docs
        entry = _WaiterEntry(expected_type, condition)
        cls._waiters[channel].append(entry)

        asyncio.create_task(RedisSubscriber._update_subscriptions())

        try:
            while True:
                event = await asyncio.wait_for(entry.queue.get(), timeout=timeout)
                if isinstance(event, expected_type) and condition(event):
                    return event
        except asyncio.TimeoutError:
            return None
        finally:
            cls._waiters[channel].remove(entry)
            asyncio.create_task(RedisSubscriber._update_subscriptions())


class RedisPubSubHandlerCogMixin:
    """Mixin for cog classes that want to handle Redis pub/sub events.

    This mixin automatically registers methods as handlers for Redis channels
    when they are decorated with the `@RedisSubscriber.subscribe` decorator.

    It also provides a `cog_unload` method to clean up handlers when the class is unloaded
    or destroyed. Nextcord will automatically invoke `cog_unload` when reloading or unloading
    the cog to ensure no stale handlers remain.

    Examples
    -------
    .. code-block:: python
        class MyCog(RedisPubSubHandlerMixin, commands.Cog):
            @RedisSubscriber.subscribe("my_channel")
            async def handle_my_event(self, event: MyProtoEnvelope):
                # Handle the event here
    """

    _registered: list[tuple[str, Callable[..., Awaitable[None]]]]

    def __init__(self) -> None:
        self._registered: list[tuple[str, Callable[..., Awaitable[None]]]] = []

        for _, member in inspect.getmembers(self, predicate=inspect.ismethod):
            channel = getattr(member, "_redis_channel", None)
            envelope = getattr(member, "_envelope_cls", None)
            if channel and envelope:
                _channel_handlers.setdefault(channel, []).append(member)
                self._registered.append((channel, member))
                logger.debug(
                    "Registered method handler %s on channel %s",
                    member.__qualname__,
                    channel,
                )

    def cog_unload(self) -> None:
        """Unregisters all method handlers from Redis channels when the cog is unloaded.

        This method is automatically called by Nextcord when the cog is unloaded or reloaded.
        It cleans up all registered handlers to prevent memory leaks and ensure that
        no stale handlers remain after the cog is removed or reloaded.
        """
        for channel, member in self._registered:
            handlers = _channel_handlers.get(channel, [])
            _channel_handlers[channel] = [h for h in handlers if h is not member]
            logger.debug(
                "Unregistered method handler %s from channel %s",
                member.__qualname__,
                channel,
            )
        self._registered.clear()
