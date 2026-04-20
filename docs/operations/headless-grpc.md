# Headless gRPC Server

SOCC can run as a headless gRPC service for other applications, automation pipelines, or custom user interfaces.

## Start the Server

Run the core engine as a gRPC service on `localhost:50051`:

```bash
npm run dev:grpc
```

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `GRPC_PORT` | `50051` | Port the gRPC server listens on |
| `GRPC_HOST` | `localhost` | Bind address; use `0.0.0.0` only behind explicit network controls |

## Run the Test CLI Client

In a separate terminal:

```bash
npm run dev:grpc:cli
```

The test client renders streamed tokens, tool activity, and permission prompts over the gRPC transport.

## Protocol Source

The active protocol definition lives in:

- `src/proto/socc.proto`

## Typical Use Cases

- embedding SOCC in an internal analyst UI
- integrating the runtime into CI or orchestration pipelines
- running a controlled terminal proxy from another application

## Operational Notes

- Keep the server bound to localhost unless you have an explicit auth and network story
- Treat bidirectional streaming and tool approvals as part of the trust boundary
- Validate provider credentials and runtime diagnostics before exposing the server to real workloads

## Related Docs

- [Runtime Hardening](runtime-hardening.md)
- [Architecture Overview](../architecture/overview.md)
