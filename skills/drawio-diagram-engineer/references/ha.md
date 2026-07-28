# High-availability architecture generation

Use `ha` when the diagram must explain redundancy, failure domains, replication, health checks, failover, RTO, or RPO.

```bash
python3 <skill-dir>/scripts/drawio_tool.py ha service.ha.json \
  -o service-ha.drawio \
  --ir-output service-ha.diagram.json \
  --preview-dir service-ha-previews \
  --strict
```

Author models against [ha.schema.json](ha.schema.json). Start from [example.ha.json](../assets/example.ha.json).

## Generated views

- **HA Topology**: components grouped by region, zone, rack, or node failure domain. Traffic, synchronous/asynchronous replication, heartbeat, and quorum links use distinct edge semantics.
- **Failover Scenarios**: one deterministic lane per failure trigger, showing detection, affected active component, promotion target, replication mode, RTO, RPO, and whether recovery is automatic.

## Quality rules

- Model at least two independent failure domains.
- Put every failover target in a different failure domain from its source.
- Give automatic failover sources an explicit health check.
- Give stateful components a replication link.
- Use at least two replicas for load balancers and active-active services.
- Use an odd quorum of at least three members.
- Treat synchronous cross-region replication as a latency risk requiring explicit review.
- State RTO and RPO as measurable objectives, not prose such as “fast recovery.”

Do not label a topology “HA” merely because it has multiple instances. The model must identify the failure boundary and the mechanism that restores service.
