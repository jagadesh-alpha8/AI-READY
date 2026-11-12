"""Bounded split recovery for oversized/truncated batches; no partial JSON is credited."""
from apps.extraction.exceptions import AIOutputTruncated, AIResponseError, RecoverableExtractionError, ProviderQuotaExhausted
from .execution import InputBudgetExceeded


def recoverable_failure(exc):
    return isinstance(exc, (AIResponseError, RecoverableExtractionError, InputBudgetExceeded)) and not isinstance(exc, ProviderQuotaExhausted)


def failure_code(exc):
    if isinstance(exc, AIOutputTruncated):
        return 'output_truncated'
    if isinstance(exc, InputBudgetExceeded):
        return 'input_budget_exceeded'
    if isinstance(exc, RecoverableExtractionError):
        return 'provider_' + (getattr(exc, 'kind', None) or 'unavailable')
    return 'invalid_response'


def request_with_split(*, service, items, identity, payload_for, schema_for, rows_for, prompt, name, result_key):
    """At most one split into two child generations. HTTP retries remain separately metered."""
    import json
    audit = {'split_attempted': False, 'requests': []}
    def request(group, phase):
        entry = {'ids': [identity(item) for item in group], 'phase': phase}
        audit['requests'].append(entry)
        try:
            response = service.extract_structured_data(system_prompt=prompt,
                user_content=json.dumps(payload_for(group), sort_keys=True), response_schema=schema_for(group), schema_name=name)
            entry['outcome'] = 'response_received'
            return response
        except Exception as exc:
            entry['outcome'] = failure_code(exc) if recoverable_failure(exc) else type(exc).__name__
            raise
    try:
        return request(items, 'initial'), audit, {}
    except (AIOutputTruncated, InputBudgetExceeded) as exc:
        code = failure_code(exc)
        if len(items) < 2:
            return {result_key: []}, audit, {identity(item): code for item in items}
    audit['split_attempted'] = True
    middle = len(items) // 2
    rows, errors = [], {}
    for group in (items[:middle], items[middle:]):
        try:
            response = request(group, 'split')
            allowed = {identity(item) for item in group}
            rows.extend(row for row in rows_for(response) if isinstance(row, dict)
                        and isinstance(row.get('condition_id'), str) and row['condition_id'] in allowed)
        except Exception as exc:
            if not recoverable_failure(exc):
                raise
            errors.update({identity(item): failure_code(exc) for item in group})
    return {result_key: rows}, audit, errors
