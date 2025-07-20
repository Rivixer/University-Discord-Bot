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
from collections.abc import Awaitable, Callable
from typing import ClassVar, get_type_hints, overload

from google.protobuf.message import Message
from redis.asyncio import Redis

_redis: Redis[bytes] | None = None

logger = logging.getLogger(__name__)


class RedisManager:
    _redis: ClassVar[Redis[bytes] | None] = None

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
    def get_redis(cls) -> Redis[bytes]:
        """Retrieves the Redis client instance.

        Returns
        -------
        Redis[bytes]
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


_channel_handlers: dict[str, list[Callable[..., Awaitable[None]]]] = {}


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


class RedisSubscriber:
    """Subscribes to channels and dispatches incoming protobuf messages to handlers."""

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
        pubsub = redis.pubsub()  # type: ignore
        channels = list(_channel_handlers.keys())
        if not channels:
            logger.warning("No channels registered for subscription.")
            return

        await pubsub.subscribe(*channels)  # type: ignore
        logger.info("Subscribed to channels: %s", channels)

        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue

            raw_channel = message["channel"]
            channel = (
                raw_channel.decode() if isinstance(raw_channel, bytes) else raw_channel
            )
            data = message.get("data")
            handlers = _channel_handlers.get(channel, [])
            if not handlers:
                logger.warning("No handler for channel %s", channel)
                continue

            for handler in handlers:
                envelope_cls = getattr(handler, "_envelope_cls")
                try:
                    envelope = envelope_cls()
                    envelope.ParseFromString(data)
                    await handler(envelope)
                except asyncio.CancelledError:
                    return
                except Exception:
                    logger.exception("Error in handler for channel %s", channel)

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


class RedisPubSubHandlerMixin:
    """Mixin for classes that want to handle Redis pub/sub events.

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
                pass
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
