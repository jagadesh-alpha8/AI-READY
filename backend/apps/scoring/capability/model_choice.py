"""Which model scores: the extraction model, or a separate one switched on with CAPABILITY_AI_API_KEY.

Off (CAPABILITY_AI_API_KEY empty): every scoring call uses get_ai_service(), as before. On: scoring calls use the
key, model and optional base URL given by CAPABILITY_AI_*, while extraction keeps its own. The effort, for Claude and
OpenAI models, is frozen in each run's execution policy (execution.policy, 'model_effort') and applied by the meter
(provider.MeteredService); Gemini keeps its own reasoning setting.
"""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

EFFORTS = ('none', 'low', 'medium', 'high', 'xhigh', 'max')
#: Calls that write or route rather than judge: they never decide a requirement's credit themselves.
WRITING = frozenset({'depth_question_plan', 'depth_question_links', 'depth_questions', 'answer_check',
                     'score_explanations', 'capability_advice', 'capability_advice_repair', 'institution_plan_parse',
                     'next_step'})
#: Gemini's reasoning levels for a Claude/OpenAI-style effort name.
GEMINI_EFFORT = {'none': 'minimal', 'low': 'low', 'medium': 'medium', 'high': 'high', 'xhigh': 'high', 'max': 'high'}


def switched_on():
    return bool(getattr(settings, 'CAPABILITY_AI_API_KEY', ''))


def scoring_model():
    """The model name scoring would use now: CAPABILITY_AI_MODEL when switched on, else AI_MODEL."""
    return settings.CAPABILITY_AI_MODEL if switched_on() else settings.AI_MODEL


def effort():
    """The configured effort for a switched-on Claude or OpenAI model, or None (the model's default)."""
    if not switched_on():
        return None
    value = getattr(settings, 'CAPABILITY_AI_EFFORT', None)
    if value is not None and value not in EFFORTS:
        raise ImproperlyConfigured(f'CAPABILITY_AI_EFFORT must be one of {", ".join(EFFORTS)} (or empty).')
    return value


def writing_effort():
    """The configured effort for writing and routing calls, or None (they use the judging effort)."""
    value = getattr(settings, 'CAPABILITY_AI_WRITING_EFFORT', None)
    if value is not None and value not in EFFORTS:
        raise ImproperlyConfigured(f'CAPABILITY_AI_WRITING_EFFORT must be one of {", ".join(EFFORTS)} (or empty).')
    return value


def tier(schema_name):
    return 'writing' if (schema_name or '') in WRITING or (schema_name or '').startswith('institution_plan_parse') \
        else 'judging'


def scoring_service():
    """The client scoring calls go through."""
    from apps.extraction.services.ai_service import get_ai_service
    if not switched_on():
        return get_ai_service()
    if not settings.CAPABILITY_AI_MODEL:
        raise ImproperlyConfigured('CAPABILITY_AI_API_KEY is set but CAPABILITY_AI_MODEL is not: name the scoring model.')
    service = get_ai_service(api_key=settings.CAPABILITY_AI_API_KEY, model=settings.CAPABILITY_AI_MODEL,
                             base_url=settings.CAPABILITY_AI_BASE_URL or '')   # never AI_BASE_URL (extraction's)
    if hasattr(service, 'json_output'):
        service.json_output = True   # Claude: JSON output (works with thinking) instead of a forced tool call
    return service
