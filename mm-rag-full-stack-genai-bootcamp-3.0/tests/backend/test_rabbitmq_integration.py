from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from backend.app.broker.messages import IngestionEventMessage
from backend.app.broker.rabbitmq import (
    RabbitMQPublisher,
    connect_rabbitmq,
    declare_ingestion_topology,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rabbitmq_quorum_topology_confirm_and_manual_ack(test_settings) -> None:
    if os.environ.get("MM_RAG_RUN_RABBITMQ_INTEGRATION_TESTS") != "1":
        pytest.skip("RabbitMQ integration tests are opt-in")

    suffix = uuid4().hex[:12]
    settings = test_settings.model_copy(
        update={
            "rabbitmq_url": test_settings.rabbitmq_url,
            "rabbitmq_exchange": f"mm-rag.test.{suffix}",
            "rabbitmq_queue": f"mm-rag.test.jobs.{suffix}",
            "rabbitmq_routing_key": f"test.job.{suffix}",
            "rabbitmq_dead_letter_exchange": f"mm-rag.test.dlx.{suffix}",
            "rabbitmq_dead_letter_queue": f"mm-rag.test.dead.{suffix}",
            "rabbitmq_dead_letter_routing_key": f"test.dead.{suffix}",
        }
    )
    if settings.rabbitmq_url is None:
        pytest.skip("RABBITMQ_URL is not configured")

    publisher = RabbitMQPublisher(settings, process_name="integration-publisher")
    connection = await connect_rabbitmq(settings, process_name="integration-consumer")
    channel = await connection.channel(publisher_confirms=False)
    exchange, queue = await declare_ingestion_topology(channel, settings)
    dead_exchange = await channel.get_exchange(settings.rabbitmq_dead_letter_exchange)
    dead_queue = await channel.get_queue(settings.rabbitmq_dead_letter_queue)
    message = IngestionEventMessage(
        event_id=uuid4(),
        event_type="ingestion.job.available",
        schema_version=1,
        job_id=uuid4(),
        occurred_at=datetime.now(UTC),
    )
    try:
        await publisher.publish(message)
        delivery = await queue.get(timeout=5, fail=False)
        assert delivery is not None
        assert IngestionEventMessage.from_body(bytes(delivery.body)) == message
        assert not delivery.processed
        await delivery.ack()
        assert delivery.processed
    finally:
        await publisher.close()
        await queue.delete(if_unused=False, if_empty=False)
        await dead_queue.delete(if_unused=False, if_empty=False)
        await exchange.delete(if_unused=False)
        await dead_exchange.delete(if_unused=False)
        await connection.close()
