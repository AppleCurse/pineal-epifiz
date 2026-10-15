# Provider catalog, connection configuration, and executable routes

This note separates three facts that must not be collapsed into the word
"supported": a provider can be listed, a connection can be configured, and a
request can be executed. It records repository behavior, not a claim that any
remote account or endpoint is live.

## 1. Three separate layers

| Layer | Source of truth | What it proves | What it does **not** prove |
|---|---|---|---|
| Catalog | `config/provider_catalog.json`, loaded by `ProviderCatalog` | A provider/model descriptor, protocol label, declared capabilities, endpoint metadata, and documented connection types can be parsed. | A credential exists, the provider is reachable, a quota is available, or a model actually honors the declared features. |
| Connection configuration | `ProviderManager.configure_connection()` and `config/router.example.json` / `PINEAL_ROUTER_CONFIG` | A tenant-scoped connection record can be constructed and its credential reference resolved at runtime. | OAuth sign-in/token refresh, a UI/API connection wizard, or a successful provider probe. |
| Execution | `RoutedChatExecutor` → `LLMGateway` | A configured, eligible route can be submitted through the gateway and recorded with its call ID and accounting. | Live success unless a real request was made and observed. Unit tests with mock transports are deterministic contract tests, not live verification. |

`ProviderManager.update_verification()` stores a verification record supplied by
its caller; it is not a connection test. New connections default to
`VerificationStatus.UNTESTED`. Do not treat a catalog entry or a connection
snapshot as a live-health result.

## 2. Current executable boundary

`ProviderProtocol` declares `openai_chat`, `openai_responses`,
`anthropic_messages`, `gemini_generate`, `cohere_chat`, and `aws_bedrock` as
possible protocol values. At repository inspection on 2026-10-15, the checked-in
catalog contains 27 provider descriptors (metadata timestamp 2026-09-02): 22
`openai_chat`, 3 `openai_responses`, 1 `anthropic_messages`, and 1 `cohere_chat`.
All 27 are marked `catalog_only`. The router runtime is narrower:

- `RoutedChatExecutor._connection_from_mapping()` accepts only `api_key` and
  `local` connection types and rejects non-`openai_chat` providers.
- `_gateway_route()` repeats the `openai_chat` execution guard.
- The generic catalog/manager model also defines `oauth_subscription`, but
  there is no OAuth authorization, refresh, or provider-specific OAuth transport
  in the routed runtime. The presence of that enum is not OAuth support.
- The catalog can describe non-OpenAI protocols without making them executable.
  For example, Anthropic Messages and OpenAI Responses descriptors need a
  protocol-specific transport/serializer before they can be routed.
- `allow_custom_base_url` in provider metadata is not by itself a runtime
  permission. `_connection_from_mapping()` rejects an endpoint override unless
  the provider is classified as `local`; other providers use their fixed
  catalog endpoint. Treat catalog URL flexibility flags as descriptive until
  an execution path actually enforces them.
- The checked-in code has no provider-connection CRUD/settings UI. Runtime
  configuration comes from the router config/environment path; the catalog is
  not an account-linking screen.

The actual routed chat requests remain under `LLMGateway`, which owns network
calls, retries, spend limits, call logging, and cancellation settlement.

## 3. Request and strategy limits

The built-in route planner filters declared `chat`, `tools`, `vision`, and
`streaming` requirements. The request boundary also derives `audio_input`,
`json_object`, and `json_schema` requirements from structured message and
`response_format` shapes. A route lacking the requested declaration is rejected
before the gateway call; the `text` format does not require an extra modality
capability. Unknown response-format types are rejected as invalid requests.
The current built-in catalog declares none of `audio_input`,
`json_object`, or `json_schema`, so those request modes currently have no
eligible catalog route in this executor.

Capability declarations are selection metadata, not runtime conformance tests.
Even a declared capability does not prove live model/provider behavior; a real
request may still fail upstream. Before adding any capability to a model
descriptor, verify the exact provider/model contract, add deterministic
request-contract tests, and report catalog evidence separately from live
verification.

| Request mode | Current behavior |
|---|---|
| Ordinary non-streaming chat | Sequential fallback can move to the next eligible route for classified retryable failures. |
| Tool definitions | Forwarded through the normal non-streaming OpenAI Chat Completions path. Returned `tool_calls` are returned to the caller; Pineal does **not** execute the caller's tools or run an automatic tool loop. |
| Fusion | Parallel candidate calls, then a separate synthesis call. Tool definitions are rejected. Text candidates are bounded before synthesis; this is not streaming. |
| Pipeline / context relay | Sequential, non-streaming candidate passes. Tool definitions are rejected. |
| Streaming | A separate single-route stream is selected after pre-stream fallback. Once a stream starts, it is pinned to that provider; there is no mid-stream provider failover. |
| Streaming + tools | Rejected by `/v1/chat/completions` with HTTP 400. The stream executor has no tool-call path. |
| Fusion/pipeline/context-relay + streaming | Rejected before any provider request. |

These are source-code contracts in `agent_core/services/routed_chat.py` and
`backend/api.py`. `tests/unit/test_routed_chat.py` checks protocol and
strategy/tool/stream guards. `tests/e2e/test_openai_compatibility.py` uses a
mock HTTP transport to check tool-call payload preservation. Neither test
establishes live provider availability or account entitlement.

## 4. Evidence vocabulary for operator-facing status

Use these distinctions in UI, logs, and reports:

1. **Catalogued** — descriptor parsed.
2. **Configured** — tenant connection and credential reference present.
3. **Eligible** — model/capability/policy/credential checks permit planning.
4. **Attempted** — a call ID was created and a request was submitted.
5. **Succeeded / failed** — the actual call returned or produced a classified error.
6. **Live-verified** — only after an explicit real endpoint probe/request with
   recorded time and outcome; a mock test or static capability flag is not this.

No credentials should be copied into documentation or chat. A missing OAuth
flow, provider transport, or feature capability is a code boundary, not something
that can be enabled by changing a feature flag alone.
