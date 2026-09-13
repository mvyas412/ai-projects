# ADR 0038: OCI container runtime boundary

- Status: Accepted
- Date: 2026-09-13
- Milestone: 8.0–8.3

## Context

The application already separates frontend, API, dispatcher, worker, databases,
broker, object storage, and observability into containers. Kubernetes would add a
control plane and operational burden that the learning scale does not justify.

## Alternatives considered

| Alternative | Advantages | Costs and risks |
| --- | --- | --- |
| OCI Kubernetes Engine | Strong orchestration learning and horizontal scale | Excess complexity and resource pressure for a free two-to-three-user pilot |
| Multiple OCI VMs | Better failure isolation | More capacity, networking, and cost pressure |
| One ARM VM with Docker Compose | Reuses verified containers and fits the learning budget | Single-host failure domain and manual capacity ceiling |

## Proposed decision

Run the Phase 8 learning environment on one Always Free-eligible OCI Ampere A1 VM
using production-specific Docker Compose overlays. Preserve distinct containers,
health checks, durable volumes, resource limits, graceful shutdown, and independent
process identities. Put an HTTPS reverse proxy in front of the frontend and FastAPI;
do not expose PostgreSQL, Qdrant, RabbitMQ, or observability administration publicly.

Build and test ARM64-compatible immutable images before provisioning. Keep the current
local Compose profile as the developer path and document Kubernetes as a future option
only when measured load or availability requirements justify it. Reuse the existing
OTLP/Collector boundary and run the bounded LGTM profile on the VM only when its
measured memory footprint leaves safe capacity for the product data plane.

## Recommendation

Approve the single-VM container boundary for this learning phase. It teaches image,
network, secret, migration, backup, and release discipline without pretending to be
highly available.

## Approval questions

1. Approve one ARM VM and Docker Compose instead of Kubernetes?
2. Approve a private data plane with only HTTPS application endpoints public?
3. Require ARM64 build and restore proof before deployment acceptance?

## Consequences

- API and workers remain logically separable but cannot scale beyond the host during
  the free pilot.
- Host loss is recovered from code, immutable images, and off-host backups.
- Multi-node and Kubernetes work remains a future evidence-driven decision.

## Decision record

Accepted by the user on 2026-09-13. The learning deployment uses one OCI ARM VM
with private Compose-managed services; Kubernetes and multi-node deployment remain
out of scope unless later evidence and budget support them.
