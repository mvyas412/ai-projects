from __future__ import annotations

import argparse
import asyncio
import os
import signal
import socket
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any

import structlog
from qdrant_client import QdrantClient

from backend.app.broker.messages import IngestionEventMessage
from backend.app.broker.rabbitmq import connect_rabbitmq, declare_ingestion_topology
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import configure_logging
from backend.app.db.session import create_database_engine, create_session_factory
from backend.app.rag.indexing import build_document_indexer
from backend.app.services.ingestion_worker import DeliveryDisposition, IngestionWorkerService
from backend.app.services.visual_ingestion import LocalVisualIngestionProcessor
from backend.app.storage.factory import create_artifact_storage, create_object_storage
from backend.app.storage.s3 import S3ObjectStorage
from backend.app.visual.extraction import DoclingStructureExtractor
from backend.app.workers.health import ProcessHealth, health_is_ready


async def _recover_expired_and_heartbeat(
    service: IngestionWorkerService,
    health: ProcessHealth,
    *,
    in_flight: int,
) -> None:
    try:
        recovered = await asyncio.to_thread(service.recover_expired)
        for _ in recovered:
            health.increment("leases_recovered")
    except Exception:
        health.increment("recovery_failed")
    # Recovery is the worker's idle path, so it must also keep readiness fresh.
    health.update(state="running", ready=True, in_flight=in_flight)


async def _run(settings: Settings) -> None:
    logger = structlog.get_logger(__name__)
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    qdrant = QdrantClient(
        url=settings.qdrant_url,
        api_key=(
            settings.qdrant_api_key.get_secret_value()
            if settings.qdrant_api_key is not None
            else None
        ),
        timeout=settings.qdrant_timeout_seconds,
        check_compatibility=False,
    )
    originals = create_object_storage(settings)
    artifacts = create_artifact_storage(settings)
    identity = f"worker-{socket.gethostname()}-{os.getpid()}"[:200]
    shutdown = threading.Event()
    visual_processor = (
        LocalVisualIngestionProcessor(
            factory,
            artifacts,
            DoclingStructureExtractor(
                settings.phase6_docling_artifacts_path,
                image_scale=settings.phase6_image_scale,
                timeout_seconds=settings.phase6_docling_timeout_seconds,
                max_pages=settings.phase6_max_pages,
            ),
            extractor_config={
                "profile": settings.phase6_extraction_profile,
                "image_scale": settings.phase6_image_scale,
                "ocr": "tesseract-cli-eng",
                "table_structure": "tableformer-accurate",
                "remote_services": False,
            },
        )
        if settings.phase6_visual_enabled
        else None
    )
    service = IngestionWorkerService(
        settings,
        factory,
        originals,
        artifacts,
        build_document_indexer(settings, qdrant),
        worker_id=identity,
        visual_processor=visual_processor,
        shutdown_requested=shutdown,
    )
    health = ProcessHealth(settings.runtime_health_directory, "worker")
    connection = await connect_rabbitmq(settings, process_name=identity)
    channel = await connection.channel(publisher_confirms=False)
    await channel.set_qos(prefetch_count=1)
    _, queue = await declare_ingestion_topology(channel, settings)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        shutdown.set()
        stop.set()

    for item in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(item, request_stop)

    in_flight: set[asyncio.Task[None]] = set()

    async def consume(message: Any) -> None:
        health.update(state="running", ready=True, in_flight=1)
        try:
            try:
                event = IngestionEventMessage.from_body(bytes(message.body))
            except (ValueError, TypeError):
                await message.reject(requeue=False)
                health.increment("dead_lettered")
                return
            disposition = await asyncio.to_thread(service.process, event)
            if disposition == DeliveryDisposition.ACK:
                await message.ack()
                health.increment("acknowledged")
            else:
                await message.reject(requeue=True)
                health.increment("requeued")
        except Exception:
            health.increment("delivery_failed")
            logger.exception("worker_delivery_failed")
            if not message.processed:
                await message.reject(requeue=True)
        finally:
            health.update(state="running", ready=True, in_flight=0)

    async def callback(message: Any) -> None:
        task = asyncio.create_task(consume(message))
        in_flight.add(task)
        task.add_done_callback(in_flight.discard)

    consumer_tag = await queue.consume(callback, no_ack=False)

    async def recover() -> None:
        while not stop.is_set():
            await _recover_expired_and_heartbeat(
                service,
                health,
                in_flight=len(in_flight),
            )
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=settings.worker_recovery_poll_seconds
                )
            except TimeoutError:
                pass

    recovery_task = asyncio.create_task(recover())
    health.update(state="running", ready=True)
    await stop.wait()
    health.update(state="draining", ready=False, in_flight=len(in_flight))
    await queue.cancel(consumer_tag)
    if in_flight:
        _, pending = await asyncio.wait(
            in_flight,
            timeout=settings.worker_shutdown_seconds,
        )
        if pending:
            health.increment("shutdown_timeout")
    recovery_task.cancel()
    await asyncio.gather(recovery_task, return_exceptions=True)
    await connection.close()
    if isinstance(originals, S3ObjectStorage):
        originals.close()
    if isinstance(artifacts, S3ObjectStorage):
        artifacts.close()
    qdrant.close()
    engine.dispose()
    health.update(state="stopped", ready=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="MM-RAG fenced ingestion worker")
    parser.add_argument("--health-check", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if args.health_check:
        path = Path(settings.runtime_health_directory) / "worker.json"
        raise SystemExit(0 if health_is_ready(path, max_age=timedelta(seconds=90)) else 1)
    configure_logging(settings.log_level)
    asyncio.run(_run(settings))


if __name__ == "__main__":
    main()
