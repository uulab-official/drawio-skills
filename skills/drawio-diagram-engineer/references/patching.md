# Semantic IR patches

Use patches for reviewable, atomic changes. A patch contains an `operations` array:

```json
{
  "operations": [
    {"op": "move-node", "id": "api", "position": {"x": 420, "y": 180}},
    {"op": "update-edge", "id": "web-api", "set": {"label": "mTLS"}},
    {
      "op": "add-node",
      "node": {"id": "worker", "label": "Worker", "kind": "service"}
    },
    {
      "op": "add-edge",
      "edge": {"id": "api-worker", "from": "api", "to": "worker", "kind": "async"}
    }
  ]
}
```

Supported operations:

- `set-diagram`
- `add-group`, `remove-group`
- `add-node`, `update-node`, `move-node`, `remove-node`
- `add-edge`, `update-edge`, `remove-edge`

For multi-page IR, add `"page": "<page-id>"` to every operation. IDs cannot be changed through an update; add a replacement and reconnect edges instead. Removing a connected node fails unless `"cascade": true` is explicit. The output is written only after the complete patched IR validates.
