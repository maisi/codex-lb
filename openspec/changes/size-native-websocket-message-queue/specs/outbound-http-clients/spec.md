## ADDED Requirements

### Requirement: Native websocket messages tolerate event bursts

The native egress client MUST buffer each websocket's received messages in a
queue bounded by both 4096 messages and 32 MiB of queued text and binary data,
the same bounds as a native HTTP stream. A message arriving at an empty queue
MUST be accepted regardless of size. When the bound is exceeded the client MUST
fail that websocket with failure phase `consumer_backpressure` and MUST NOT
block the helper reader shared by other requests.

#### Scenario: A late consumer receives a reasoning burst intact

- **GIVEN** a native Responses websocket whose consumer is not reading
- **WHEN** the helper delivers 500 frames and then a close
- **THEN** the consumer later receives all 500 frames in order followed by the close

#### Scenario: A consumer that stops draining is failed

- **WHEN** queued messages exceed the bound before the consumer reads
- **THEN** the consumer receives `Upstream websocket receive failed (consumer_backpressure)`
