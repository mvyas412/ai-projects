from __future__ import annotations

from typing import Any

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message

from backend.app.broker.messages import IngestionEventMessage
from backend.app.core.config import Settings


class BrokerConnectionError(Exception):
    """Safe broker connectivity failure."""


class BrokerPublishError(Exception):
    """Safe ambiguous or rejected publication failure."""


async def connect_rabbitmq(settings: Settings, *, process_name: str) -> Any:
    try:
        return await aio_pika.connect_robust(
            settings.require_rabbitmq_url(),
            timeout=settings.rabbitmq_connect_timeout_seconds,
            client_properties={"connection_name": process_name[:128]},
        )
    except Exception as exc:
        raise BrokerConnectionError("RabbitMQ connection failed") from exc


async def declare_ingestion_topology(channel: Any, settings: Settings) -> tuple[Any, Any]:
    """Idempotently declare the accepted durable exchange, quorum queue, and DLQ."""

    dead_exchange = await channel.declare_exchange(
        settings.rabbitmq_dead_letter_exchange,
        ExchangeType.DIRECT,
        durable=True,
    )
    dead_queue = await channel.declare_queue(
        settings.rabbitmq_dead_letter_queue,
        durable=True,
        arguments={"x-queue-type": "quorum"},
    )
    await dead_queue.bind(
        dead_exchange,
        routing_key=settings.rabbitmq_dead_letter_routing_key,
    )

    exchange = await channel.declare_exchange(
        settings.rabbitmq_exchange,
        ExchangeType.DIRECT,
        durable=True,
    )
    queue = await channel.declare_queue(
        settings.rabbitmq_queue,
        durable=True,
        arguments={
            "x-queue-type": "quorum",
            "x-dead-letter-exchange": settings.rabbitmq_dead_letter_exchange,
            "x-dead-letter-routing-key": settings.rabbitmq_dead_letter_routing_key,
            "x-delivery-limit": 5,
        },
    )
    await queue.bind(exchange, routing_key=settings.rabbitmq_routing_key)
    return exchange, queue


class RabbitMQPublisher:
    """Confirmed persistent publication behind a small dispatcher-facing adapter."""

    def __init__(self, settings: Settings, *, process_name: str) -> None:
        self._settings = settings
        self._process_name = process_name
        self._connection: Any | None = None
        self._channel: Any | None = None
        self._exchange: Any | None = None

    async def connect(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            return
        self._connection = await connect_rabbitmq(
            self._settings,
            process_name=self._process_name,
        )
        self._channel = await self._connection.channel(
            publisher_confirms=True,
            on_return_raises=True,
        )
        self._exchange, _ = await declare_ingestion_topology(
            self._channel,
            self._settings,
        )

    async def publish(self, message: IngestionEventMessage) -> None:
        await self.connect()
        assert self._exchange is not None
        try:
            result = await self._exchange.publish(
                Message(
                    body=message.broker_body(),
                    content_type="application/json",
                    delivery_mode=DeliveryMode.PERSISTENT,
                    message_id=str(message.event_id),
                    correlation_id=str(message.event_id),
                    timestamp=message.occurred_at,
                    type=message.event_type,
                    app_id="mm-rag-outbox-dispatcher",
                ),
                routing_key=self._settings.rabbitmq_routing_key,
                mandatory=True,
                timeout=self._settings.rabbitmq_publish_timeout_seconds,
            )
        except Exception as exc:
            raise BrokerPublishError("RabbitMQ publication was not confirmed") from exc
        if result is None or result.__class__.__name__ != "Ack":
            raise BrokerPublishError("RabbitMQ publication was not confirmed")

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None
        self._channel = None
        self._exchange = None
