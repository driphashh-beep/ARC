# ARC Protocol

This document defines the smallest transport-neutral protocol for registering and
executing ARC functions. It is intentionally self-contained: a host may use a
CLI, an in-process call, or a future transport without changing the message
contract.

## Scope

ARC consists of a function registry and an execution lifecycle. The protocol
does not prescribe a network, persistence layer, authentication mechanism, or
programming language.

## Lifecycle

An ARC host follows these phases:

1. **Initialize**: create an empty registry and assign a protocol version.
2. **Register**: add each function by its unique name and validate its
   descriptor.
3. **Ready**: accept execution requests only after registration succeeds.
4. **Execute**: resolve the function, validate input, invoke it once, and
   return a response.
5. **Shutdown**: stop accepting requests and release host resources.

Registration failure prevents the host from entering `ready`. An execution
request received before `ready` or after `shutdown` is rejected.

## Message Envelope

Every message is a JSON object with this shape:

```json
{
  "protocol": "arc/1",
  "type": "execute",
  "requestId": "req-001",
  "function": "math.add",
  "input": {"left": 2, "right": 3}
}
```

Required fields:

- `protocol`: exact protocol identifier, currently `arc/1`.
- `type`: `execute`, `result`, or `error`.
- `requestId`: non-empty string chosen by the caller. It is echoed in the
  response and must be unique among in-flight requests.

`execute` messages also require `function` and may provide any JSON value in
`input`. If omitted, `input` is treated as `null`.

A successful response is:

```json
{
  "protocol": "arc/1",
  "type": "result",
  "requestId": "req-001",
  "output": 5
}
```

An error response is:

```json
{
  "protocol": "arc/1",
  "type": "error",
  "requestId": "req-001",
  "error": {
    "code": "FUNCTION_NOT_FOUND",
    "message": "No function is registered as math.subtract"
  }
}
```

Error `code` values are stable machine-readable identifiers. `message` is
diagnostic text and must not be used for branching.

## Function Registration

Each function is registered with a descriptor and an implementation:

```json
{
  "name": "math.add",
  "description": "Add two numbers",
  "input": {
    "type": "object",
    "required": ["left", "right"]
  }
}
```

Registration rules:

- Names are non-empty, case-sensitive strings using dot-separated segments.
- A name may be registered only once in a registry.
- The descriptor is metadata; the host remains responsible for actual input
  validation.
- Implementations accept exactly one input value and return one JSON-compatible
  output value.
- Implementations must not mutate the request envelope.
- A function must be deterministic for the same input unless its descriptor
  explicitly documents side effects or external state.

## Execution Rules

For each `execute` message, the host must:

1. Validate the envelope and protocol identifier.
2. Reject unknown functions with `FUNCTION_NOT_FOUND`.
3. Validate `input` with the registered descriptor, returning
   `INVALID_INPUT` when it does not match.
4. Invoke the implementation once.
5. Return either `result` or `error` with the same `requestId`.

The host must never expose implementation stack traces in an error message.
Unexpected implementation failures use `EXECUTION_FAILED`. A request is not
retried implicitly; retry policy belongs to the caller.

The minimum error codes are:

- `INVALID_ENVELOPE`: required fields are missing or have the wrong type.
- `UNSUPPORTED_PROTOCOL`: the protocol identifier is not supported.
- `HOST_NOT_READY`: the lifecycle does not accept execution yet.
- `FUNCTION_NOT_FOUND`: no matching registration exists.
- `DUPLICATE_FUNCTION`: a name is already registered.
- `INVALID_INPUT`: input fails the function contract.
- `EXECUTION_FAILED`: the implementation could not produce a result.

## Initiation Example

A host can initiate the protocol by creating a registry, registering
`math.add`, marking itself `ready`, and sending this request:

```json
{
  "protocol": "arc/1",
  "type": "execute",
  "requestId": "req-001",
  "function": "math.add",
  "input": {"left": 2, "right": 3}
}
```

The expected result is `5`, wrapped in the `result` envelope shown above.

## Current Boundary

This workspace contains ARC assets and agent instructions but no executable
runtime, test runner, transport, or domain-specific function definitions. No
implementation or external integration is included until those choices are
specified.