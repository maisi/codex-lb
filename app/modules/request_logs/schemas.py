from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.modules.shared.schemas import DashboardModel


class RequestLogCostBreakdown(DashboardModel):
    input_usd: float | None = None
    cached_input_usd: float | None = None
    output_usd: float | None = None
    total_usd: float | None = None


class RequestLogEntry(DashboardModel):
    sticky_key_source: str | None = None
    sticky_kind: str | None = None
    sticky_key_hash: str | None = None
    requested_at: datetime
    conversation_id: str | None = None
    account_id: str | None = None
    plan_type: str | None = None
    api_key_id: str | None = None
    api_key_name: str | None = None
    request_id: str
    archive_request_id: str | None = None
    request_kind: str = "normal"
    connection_request_kind: str | None = None
    model: str
    source: str | None = None
    model_source_id: str | None = None
    model_source_kind: str | None = None
    useragent: str | None = None
    useragent_group: str | None = None
    client_ip: str | None = None
    transport: str | None = None
    upstream_transport: str | None = None
    upstream_proxy_route_mode: str | None = None
    upstream_proxy_pool_id: str | None = None
    upstream_proxy_endpoint_id: str | None = None
    upstream_proxy_fallback_used: bool | None = None
    upstream_proxy_fail_closed_reason: str | None = None
    service_tier: str | None = None
    requested_service_tier: str | None = None
    actual_service_tier: str | None = None
    status: str
    error_code: str | None = None
    error_message: str | None = None
    failure_phase: str | None = None
    failure_detail: str | None = None
    failure_exception_type: str | None = None
    upstream_status_code: int | None = None
    upstream_error_code: str | None = None
    bridge_stage: str | None = None
    tokens: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    output_tokens_raw: int | None = None
    reasoning_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_effort: str | None = None
    cost_usd: float | None = None
    cost_breakdown: RequestLogCostBreakdown = Field(default_factory=RequestLogCostBreakdown)
    latency_ms: int | None = None
    latency_first_token_ms: int | None = None
    latency_queue_ms: int | None = None


class RequestLogConversation(DashboardModel):
    request_count: int
    aggregated_cost_usd: float


class RequestLogsResponse(DashboardModel):
    requests: list[RequestLogEntry] = Field(default_factory=list)
    total: int
    has_more: bool
    conversation: RequestLogConversation | None = None


class RequestLogModelOption(DashboardModel):
    model: str
    reasoning_effort: str | None = None


class RequestLogApiKeyOption(DashboardModel):
    id: str
    name: str
    key_prefix: str | None = None


class RequestLogFilterOptionsResponse(DashboardModel):
    account_ids: list[str] = Field(default_factory=list)
    model_options: list[RequestLogModelOption] = Field(default_factory=list)
    api_keys: list[RequestLogApiKeyOption] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)


class ConversationModelEffort(DashboardModel):
    model: str
    reasoning_effort: str | None = None


class ConversationModelStat(DashboardModel):
    model_effort: ConversationModelEffort
    reqs: int
    total_elapsed_time: int
    total_input_tokens: int
    cached_input_tokens: int | None
    total_output_tokens: int
    total_cost_usd: float


class ConversationEntry(DashboardModel):
    conversation_id: str
    first_request: datetime
    last_request: datetime
    request_count: int
    representative_account: str | None = None
    remaining_account_count: int
    api_key_id: str | None = None
    api_key_name: str | None = None
    representative_model: str | None = None
    remaining_model_count: int
    total_tokens: int
    cached_input_tokens: int | None
    total_cost_usd: float


class ConversationsResponse(DashboardModel):
    conversations: list[ConversationEntry] = Field(default_factory=list)
    total: int
    has_more: bool


class ConversationDetailsResponse(DashboardModel):
    conversation_id: str
    start: datetime
    latest: datetime
    account_count: int
    total_elapsed_time: int
    dominant_useragent_group: str | None = None
    model_stats: list[ConversationModelStat] = Field(default_factory=list)


class RoutingCandidateResponse(DashboardModel):
    account_id: str
    rank: int | None = None
    routing_policy: str
    status: str
    health: str
    primary_used_percent: float | None = None
    secondary_used_percent: float | None = None
    over_budget_threshold: bool
    eligible: bool
    overload_backoff: bool
    unavailable_reason: str | None = None


class RoutingAttemptResponse(DashboardModel):
    attempt: int
    recorded_at: datetime
    api_key_id: str | None = None
    model: str | None = None
    routing_strategy: str
    sticky_kind: str | None = None
    sticky_owner_account_id: str | None = None
    outcome: str
    selected_account_id: str | None = None
    serving_rank: int | None = None
    decided_by: str | None = None
    owner_flags: dict[str, bool] = Field(default_factory=dict)
    budget_threshold_pct: float
    key_ranks_accounts: bool
    excluded_account_ids: list[str] = Field(default_factory=list)
    ranked_accounts_not_offered: list[str] = Field(default_factory=list)
    candidates: list[RoutingCandidateResponse] = Field(default_factory=list)
    error_code: str | None = None


class RequestRoutingResponse(DashboardModel):
    request_id: str
    # Empty when the request is older than the in-memory trace window, was
    # served by another replica, or never reached account selection.
    attempts: list[RoutingAttemptResponse] = Field(default_factory=list)
