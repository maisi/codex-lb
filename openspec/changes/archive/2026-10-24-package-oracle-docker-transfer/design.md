## Context

Both images copy an isolated Python environment from a build stage. Runtime images omit pip/uv, so installing the optional driver interactively is not a durable deployment path. The transfer currently exists only in this checkout, not a published release.

## Goals / Non-Goals

Support the existing Oracle CLI and runtime from both images without changing SQLite defaults. Publishing images, executing a production migration, and Docker daemon administration are outside this change.

## Decisions

Install the existing locked `oracle` extra in both dependency stages. Keep normal startup unchanged. Use `--entrypoint python ... -m app.db.migrate` for one-shot commands so the normal startup migration cannot run before a dry run. Reuse the stopped container's mounts with `--volumes-from`; retain its complete data directory/key/archive continuity.

## Risks / Trade-offs

The additional driver increases image size. Reusing the dependency lock avoids an untracked install. Volume inheritance does not inherit environment or networks: document original configuration, container-reachable Oracle host, optional wallet and network mounts. Images must be built from the updated checkout until published.
