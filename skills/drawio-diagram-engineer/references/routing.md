# Ports and orthogonal routing

The compiler assigns deterministic ports and bend points to every edge. Automatic routing:

- chooses the side facing the target;
- distributes fan-out and fan-in endpoints from `0.18` to `0.82`;
- evaluates horizontal and vertical corridor candidates;
- prioritizes avoiding nodes, then unrelated edge crossings, bend count, and length;
- emits the same route into editable draw.io XML and dependency-free SVG.

## Explicit ports

Set edge ports in `style` when topology meaning or review clarity requires a fixed attachment:

```json
{
  "id": "monitor-api",
  "from": "monitor",
  "to": "api",
  "label": "health",
  "kind": "association",
  "style": {
    "source_port": "south",
    "source_offset": 0.5,
    "target_port": "north",
    "target_offset": 0.75
  }
}
```

`source_port` and `target_port` accept `auto`, `north`, `east`, `south`, or `west`. Offsets are numbers from `0` to `1`, measured left-to-right on north/south sides and top-to-bottom on east/west sides.

Omit offsets to let the compiler distribute endpoints. Prefer automatic routing first. Use explicit values for monitoring lines, fixed network interfaces, return paths, or a deliberately reserved routing corridor.

## Review rules

- Do not assign the same explicit side and offset to several unrelated edges.
- Keep ports on the side that matches the reading direction unless the relationship has a clear spatial meaning.
- Run `audit` after changing positions or ports. It checks actual waypoint segments for node intersections and unrelated edge crossings.
- Treat port and route changes as presentation changes. Semantic architecture `diff` intentionally ignores edge `style`.
