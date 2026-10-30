import os
import sys
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# settings.py -> config -> backend (BASE_DIR)
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-default-key-change-me')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# The frontend's axios client calls every endpoint without a trailing slash
# (e.g. '/api/v1/sprints'). Django's default APPEND_SLASH redirect turns POST
# bodies into dropped GETs on redirect, so every URL below is defined without
# a trailing slash and this redirect behaviour is disabled to match.
APPEND_SLASH = False

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'django_filters',
    'corsheaders',
    'drf_spectacular',

    # Local apps
    'apps.accounts',
    'apps.institutions',
    'apps.sprints',
    'apps.documents',
    'apps.extraction',
    'apps.facts',
    'apps.gaps',
    'apps.scoring',
    'apps.recommendations',
    'apps.benchmarks',
    'apps.assessments',
    'apps.reports',
    'apps.dashboard',
    'apps.vector_store',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # Logs API requests that are slow or run many queries (no contents): config/request_diagnostics.py.
    'config.request_diagnostics.RequestDiagnosticsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Rate-limits POSTs to the Django admin login page (DRF throttles cover the API).
    'config.security.AdminLoginRateLimitMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases
import dj_database_url

DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Document uploads (NAAC SSR, AQAR, faculty lists, etc.) can run up to 50MB.
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('DATA_UPLOAD_MAX_MEMORY_SIZE', 50 * 1024 * 1024))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('FILE_UPLOAD_MAX_MEMORY_SIZE', 50 * 1024 * 1024))

# Business-rule cap enforced by apps.documents (returns a clean 400 via the
# serializer, rather than relying solely on Django's lower-level request
# parsing limits above).
MAX_DOCUMENT_UPLOAD_SIZE = int(os.getenv('MAX_DOCUMENT_UPLOAD_SIZE', 50 * 1024 * 1024))

# apps.gaps automatic gap-generation thresholds. A fact below the low
# threshold gets a `low_confidence` gap; below the very-low threshold that
# gap is `high` priority instead of `medium`. Documents uploaded longer ago
# than GAP_STALE_DATA_DAYS get a `stale_data` gap.
GAP_LOW_CONFIDENCE_THRESHOLD = float(os.getenv('GAP_LOW_CONFIDENCE_THRESHOLD', 0.7))
GAP_VERY_LOW_CONFIDENCE_THRESHOLD = float(os.getenv('GAP_VERY_LOW_CONFIDENCE_THRESHOLD', 0.5))
GAP_STALE_DATA_DAYS = int(os.getenv('GAP_STALE_DATA_DAYS', 365))

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'accounts.User'

# REST Framework Settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Brute-force protection on sign-in (see apps.accounts.views.LoginView):
    # per client address and, separately, per email address being tried.
    # (Effectively unlimited under `manage.py test`, where every test signs in
    # through the real endpoint; the throttle tests override these.)
    'DEFAULT_THROTTLE_RATES': (
        {'login': '10000/minute', 'login_email': '10000/minute', 'password_change': '10000/minute',
         'password_reset': '10000/minute', 'password_reset_email': '10000/minute', 'invitation': '10000/minute'}
        if ((len(sys.argv) > 1 and sys.argv[1] == 'test') or 'pytest' in sys.modules or any('pytest' in arg for arg in sys.argv)) else {
            'login': os.getenv('LOGIN_RATE_PER_IP', '10/minute'),
            'login_email': os.getenv('LOGIN_RATE_PER_EMAIL', '20/hour'),
            'password_change': '10/hour',
            # "Forgot password": per client address and per email address.
            'password_reset': '10/hour',
            'password_reset_email': '3/hour',
            # IQAC Coordinator invitation links (check / activate), per client address.
            'invitation': '20/hour',
        }
    ),
    # Number of reverse proxies in front of Django (nginx = 1 in production).
    # With 0, every request appears to come from the nginx container and all
    # users would share one throttle bucket; with 1, the real client address
    # is read from the X-Forwarded-For entry nginx appends.
    'NUM_PROXIES': int(os.getenv('TRUSTED_PROXY_COUNT', 0)),
}

# Cache: used by the login throttles, the admin-login limit and the watcher's
# one-run-at-a-time lock, so it must be shared by every process. Production
# points DJANGO_CACHE_URL at Redis (docker-compose.yml); without it each
# process keeps its own in-memory cache, which is fine for one dev server.
_CACHE_URL = os.getenv('DJANGO_CACHE_URL', '')
CACHES = {
    'default': (
        {'BACKEND': 'django.core.cache.backends.redis.RedisCache', 'LOCATION': _CACHE_URL,
         'KEY_PREFIX': 'aiready', 'TIMEOUT': 300}
        if _CACHE_URL and not (len(sys.argv) > 1 and sys.argv[1] == 'test')
        else {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'aiready'}
    ),
}

# Email: password-reset links and error reports to ADMINS. With EMAIL_HOST_USER
# set, mail goes out over SMTP (Gmail by default: use an app password, not the
# account password); without it, mail is printed to the console (development).
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_TIMEOUT = 15
EMAIL_BACKEND = (
    'django.core.mail.backends.smtp.EmailBackend' if EMAIL_HOST_USER
    else 'django.core.mail.backends.console.EmailBackend'
)
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', f'InGage AI Readiness <{EMAIL_HOST_USER or "noreply@localhost"}>')
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Who gets an email for every server error (HTTP 500) in production.
ADMINS = [('Admin', a.strip()) for a in os.getenv('ADMIN_EMAILS', '').split(',') if a.strip()]
# Where links in emails point (the site users open), e.g. https://ai.ingageedutech.com
FRONTEND_BASE_URL = os.getenv('FRONTEND_BASE_URL', 'http://localhost:3000').rstrip('/')
# A password-reset link works once and expires after this many seconds.
PASSWORD_RESET_TIMEOUT = int(os.getenv('PASSWORD_RESET_TIMEOUT', 60 * 60))
# IQAC Coordinator invitation links (apps/institutions/coordinator.py): single use, valid this many hours.
COORDINATOR_INVITATION_HOURS = int(os.getenv('COORDINATOR_INVITATION_HOURS', 72))

# Interactive API docs (/api/docs, /api/redoc, /api/schema): on in development,
# off in production unless API_DOCS_ENABLED=true -- they map every endpoint.
API_DOCS_ENABLED = os.getenv('API_DOCS_ENABLED', 'True' if DEBUG else 'False') == 'True'
ADMIN_LOGIN_RATE = os.getenv('ADMIN_LOGIN_RATE', '10/minute')

# Simple JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(os.getenv('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', 60))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(os.getenv('JWT_REFRESH_TOKEN_LIFETIME_DAYS', 1))),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': os.getenv('JWT_SECRET_KEY', SECRET_KEY),
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_SET_URL': None,
    'LEEWAY': 0,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'JTI_CLAIM': 'jti',
}

# CORS Settings
CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',')

# Spectacular Settings
SPECTACULAR_SETTINGS = {
    'TITLE': 'AIOS Discovery Sprint API',
    'DESCRIPTION': 'Backend API for AI Readiness Discovery Sprint platform',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Celery Settings
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
# Nothing in this project calls .get()/.result on a task's AsyncResult --
# every task's outcome is tracked in its own DB row (ExtractionJob) instead.
# Without this, Celery still tries to record task state through the redis
# result backend on every .delay() call; when Redis is down that triggers
# the backend's own ~20-attempt reconnect cascade (~100s) before the
# broker-unreachable error this project already handles gracefully ever
# gets a chance to raise. Ignoring results skips that entirely.
CELERY_TASK_IGNORE_RESULT = True
# Each worker slot takes one job at a time, so a sprint's documents go to
# whichever slot frees up next instead of piling up behind a busy one.
CELERY_WORKER_PREFETCH_MULTIPLIER = int(os.getenv('CELERY_WORKER_PREFETCH_MULTIPLIER', 1))
# Worker pool and size, so `celery -A config worker` needs no flags: e.g.
# CELERY_WORKER_POOL=threads + CELERY_WORKER_CONCURRENCY=8 on Windows (where
# the default prefork pool doesn't work) to run 8 extraction jobs at once.
if os.getenv('CELERY_WORKER_POOL'):
    CELERY_WORKER_POOL = os.getenv('CELERY_WORKER_POOL')
# CELERY_WORKER_CONCURRENCY is set further down, from AI_PROCESSING_MODE.
# Tasks are acks_late: Redis hands an unacknowledged task to another worker
# after this long. Must outlast the slowest document, or a long one would be
# processed twice.
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'visibility_timeout': int(os.getenv('CELERY_VISIBILITY_TIMEOUT_SECONDS', 6 * 60 * 60)),
}
# The only periodic job: the Stage 4 source watcher (checks the official pages
# of ENABLED source feeds once a day and records changes for review). It needs
# a beat process (`celery -A config beat`) and WATCHER_ENABLED=true; off by
# default so a dev machine never contacts government sites by surprise.
# Benchmark Studio is read-only: the manager-provided workbooks are the standard catalogue (sources, indicators,
# levels, applicability, source mappings). The portal only views it; it changes through the controlled workbook
# import commands (dry run first), never through portal add / edit / delete, AI drafting, the watcher or candidates.
# The API enforces it (apps/benchmarks/permissions.py). false = the earlier authoring workflows (maintenance only).
BENCHMARK_CATALOGUE_READ_ONLY = os.getenv('BENCHMARK_CATALOGUE_READ_ONLY', 'true').lower() in ('1', 'true', 'yes')
WATCHER_ENABLED = (os.getenv('WATCHER_ENABLED', 'false').lower() in ('1', 'true', 'yes')
                   and not BENCHMARK_CATALOGUE_READ_ONLY)
WATCHER_HOUR_UTC = int(os.getenv('WATCHER_HOUR_UTC', 20))  # 20:30 UTC = 02:00 IST
CELERY_BEAT_SCHEDULE = {}

# Extraction job recovery (apps/extraction/services/recovery.py): every EXTRACTION_RECOVERY_INTERVAL_SECONDS the
# beat process re-queues jobs whose queue message or worker was lost (PostgreSQL is the source of truth).
# EXTRACTION_STALE_SECONDS: a running job with no heartbeat for this long lost its worker -- keep it well above
#   AI_REQUEST_TIMEOUT_SECONDS x (AI_SDK_MAX_RETRIES + 1), the longest a healthy worker can go between heartbeats.
# EXTRACTION_RECOVERY_PENDING_SECONDS: a queued / retrying job this overdue whose task id the broker no longer
#   holds lost its message. EXTRACTION_RECOVERY_GRACE_SECONDS: a job created this long ago and never published.
EXTRACTION_RECOVERY_ENABLED = os.getenv('EXTRACTION_RECOVERY_ENABLED', 'true').lower() in ('1', 'true', 'yes')
EXTRACTION_RECOVERY_INTERVAL_SECONDS = int(os.getenv('EXTRACTION_RECOVERY_INTERVAL_SECONDS', 300))
EXTRACTION_STALE_SECONDS = int(os.getenv('EXTRACTION_STALE_SECONDS', 30 * 60))
EXTRACTION_RECOVERY_PENDING_SECONDS = int(os.getenv('EXTRACTION_RECOVERY_PENDING_SECONDS', 15 * 60))
EXTRACTION_RECOVERY_GRACE_SECONDS = int(os.getenv('EXTRACTION_RECOVERY_GRACE_SECONDS', 120))
EXTRACTION_RECOVERY_BATCH = int(os.getenv('EXTRACTION_RECOVERY_BATCH', 50))
EXTRACTION_RECOVERY_DEAD_WORKER_SECONDS = int(os.getenv('EXTRACTION_RECOVERY_DEAD_WORKER_SECONDS', 180))
if EXTRACTION_RECOVERY_ENABLED:
    CELERY_BEAT_SCHEDULE['extraction-job-recovery'] = {
        'task': 'apps.extraction.tasks.recover_extraction_jobs',
        'schedule': float(EXTRACTION_RECOVERY_INTERVAL_SECONDS),
    }

# Named queues (optional). Empty = Celery's default queue for everything, as before. Set both to separate
# OCR-heavy page reading from AI extraction so each gets its own worker service and concurrency
# (docker-compose: the `celery-ocr` worker, profile "ocr-queue"):
#   OCR_QUEUE=ocr  EXTRACTION_QUEUE=extraction
# Then a document is read (text + OCR) by tasks.read_document_pages on OCR_QUEUE first, and its AI extraction runs
# on EXTRACTION_QUEUE, reusing the saved pages. Worker services must listen on the matching queue (-Q).
EXTRACTION_QUEUE = os.getenv('EXTRACTION_QUEUE', '').strip()
OCR_QUEUE = os.getenv('OCR_QUEUE', '').strip()
CELERY_TASK_ROUTES = {}
if EXTRACTION_QUEUE:
    CELERY_TASK_ROUTES['apps.extraction.tasks.run_extraction_job'] = {'queue': EXTRACTION_QUEUE}
    CELERY_TASK_ROUTES['apps.extraction.tasks.recover_extraction_jobs'] = {'queue': EXTRACTION_QUEUE}
if OCR_QUEUE:
    CELERY_TASK_ROUTES['apps.extraction.tasks.read_document_pages'] = {'queue': OCR_QUEUE}
if WATCHER_ENABLED:
    from celery.schedules import crontab
    CELERY_BEAT_SCHEDULE['daily-source-watcher'] = {
        'task': 'apps.benchmarks.tasks.run_source_watcher',
        'schedule': crontab(hour=WATCHER_HOUR_UTC, minute=30),
        'kwargs': {'trigger': 'schedule'},
    }

# AI provider -- apps.extraction.services.ai_service.get_ai_service() picks
# OpenAI or Anthropic purely from which of these keys is set and what its
# format looks like (see that module for the detection logic), so switching
# providers is "paste a different key here," never a code change. AI_MODEL
# is an optional override for either provider; each provider otherwise gets
# its own sensible default (see ai_service.DEFAULT_MODELS).
#
# AI_BASE_URL points at an OpenAI-*compatible* endpoint instead of OpenAI
# itself -- a local model router, a self-hosted gateway, a proxy in front of
# several providers, etc. When set, it wins over key-format detection
# entirely: a custom base URL already tells get_ai_service() exactly where
# to send requests, so it doesn't matter whether the key looks like a real
# OpenAI/Anthropic key. AI_MODEL must be set too in this case -- there's no
# sensible default model for an endpoint this app knows nothing about.
#
# OPENAI_API_KEY/OPENAI_EXTRACTION_MODEL are kept, unchanged, for anyone
# already using them from before multi-provider support existed -- they're
# just "the configured key/model" as far as get_ai_service() is concerned.
#
# Deliberately left unset-safe here so Django boots fine without any of
# these -- the service classes themselves raise a clear error if the key/
# model they need is missing at the point something actually tries to use it.
AI_API_KEY = os.getenv('AI_API_KEY', '')
AI_MODEL = os.getenv('AI_MODEL', '')
AI_BASE_URL = os.getenv('AI_BASE_URL', '')
# Large local-model extraction requests can take longer than hosted API calls.
# Keep the timeout configurable for both OpenAI-compatible and Anthropic clients.
AI_REQUEST_TIMEOUT_SECONDS = int(os.getenv('AI_REQUEST_TIMEOUT_SECONDS', '300'))
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_EXTRACTION_MODEL = os.getenv('OPENAI_EXTRACTION_MODEL', '')
# Extra / overriding AI prices (USD per 1M tokens) as JSON -- see
# apps.extraction.pricing, e.g. {"my-combo": {"input": 0, "output": 0}}.
AI_PRICING_JSON = os.getenv('AI_PRICING_JSON', '')

# Several OpenAI-compatible routers to spread extraction jobs across -- see
# apps.extraction.services.router_pool. Empty = the single AI_BASE_URL above.
# AI_ROUTER_URLS: comma-separated base URLs (a missing /v1 is added).
# AI_ROUTER_API_KEYS: one key per router in the same order, or one key for all
#   (empty = AI_API_KEY). Every router must serve AI_MODEL.
# AI_ROUTER_MAX_CONCURRENT: jobs one router runs at once.
# AI_ROUTER_WAIT_SECONDS: how long a job waits for a free router before retrying.
# AI_ROUTER_LEASE_SECONDS: a slot held by a crashed worker frees itself after this.
# AI_ROUTER_COOLDOWN_SECONDS: a router that just failed is used last for this long.
AI_ROUTER_URLS = os.getenv('AI_ROUTER_URLS', '')
AI_ROUTER_API_KEYS = os.getenv('AI_ROUTER_API_KEYS', '')
AI_ROUTER_MAX_CONCURRENT = int(os.getenv('AI_ROUTER_MAX_CONCURRENT', 2))
AI_ROUTER_WAIT_SECONDS = int(os.getenv('AI_ROUTER_WAIT_SECONDS', 300))
AI_ROUTER_LEASE_SECONDS = int(os.getenv('AI_ROUTER_LEASE_SECONDS', 30 * 60))
AI_ROUTER_COOLDOWN_SECONDS = int(os.getenv('AI_ROUTER_COOLDOWN_SECONDS', 60))
AI_ROUTER_REDIS_URL = os.getenv('AI_ROUTER_REDIS_URL', '')  # empty = CELERY_BROKER_URL
# A router whose provider is out of quota/credit gets no new jobs until `manage.py ai_router_reactivate`.
# When no router is left, a job waits (status "retrying", with the reason) and checks again every
# AI_ROUTER_EXHAUSTED_RETRY_SECONDS, at most AI_ROUTER_EXHAUSTED_MAX_WAITS times, then fails with the reason.
AI_ROUTER_EXHAUSTED_RETRY_SECONDS = int(os.getenv('AI_ROUTER_EXHAUSTED_RETRY_SECONDS', 15 * 60))
AI_ROUTER_EXHAUSTED_MAX_WAITS = int(os.getenv('AI_ROUTER_EXHAUSTED_MAX_WAITS', 8))
# Model every router serves (e.g. a 9router combo); empty = AI_MODEL. Separate so
# switching AI_PROCESSING_MODE needs no other edit when the two setups differ.
AI_ROUTER_MODEL = os.getenv('AI_ROUTER_MODEL', '')

# Which of the two AI processing methods is active -- the only switch; see
# config/ai_processing_mode.py. 'single' (default): AI_BASE_URL alone, 2 worker
# slots. 'multi_router': the routers above, AI_ROUTER_MAX_CONCURRENT slots each.
# An invalid value stops the app from starting. Restart the Celery worker after
# changing it (switch-ai-mode.ps1 does that).
from config.ai_processing_mode import default_worker_concurrency, parse_mode, router_count  # noqa: E402

AI_PROCESSING_MODE = parse_mode(os.getenv('AI_PROCESSING_MODE'))
# Worker slots: CELERY_WORKER_CONCURRENCY wins when set, else what the mode needs.
CELERY_WORKER_CONCURRENCY = int(os.getenv('CELERY_WORKER_CONCURRENCY') or default_worker_concurrency(
    AI_PROCESSING_MODE, routers=router_count(AI_ROUTER_URLS), per_router=AI_ROUTER_MAX_CONCURRENT,
))

# apps.extraction.services.openai_classifier: how many pages of a document's
# extracted text get sampled and sent to OpenAI for classification.
OPENAI_CLASSIFICATION_SAMPLE_PAGES = int(os.getenv('OPENAI_CLASSIFICATION_SAMPLE_PAGES', 3))
# The AI's category counts toward the Upload Data Pack checklist only at or
# above this confidence (0-1); below it the document shows "Needs review".
AI_CLASSIFICATION_MIN_CONFIDENCE = float(os.getenv('AI_CLASSIFICATION_MIN_CONFIDENCE', 0.7))
# An extracted fact's AI-QIF indicator tag counts as "mapped" at or above this
# confidence (0-1); below it the tag shows "Needs review". Category only --
# it doesn't affect CRI scoring.
AIQIF_MAPPING_MIN_CONFIDENCE = float(os.getenv('AIQIF_MAPPING_MIN_CONFIDENCE', 0.7))
# Extracted facts with AI confidence strictly above this are confirmed automatically at the end of extraction
# (apps/facts/auto_confirm.py) -- unless in an open conflict or their number is not in their quote. Recorded
# as the system account, so they stay distinguishable from a person's confirmation. 'off' (or empty) disables.
_auto_confirm = os.getenv('FACT_AUTO_CONFIRM_MIN_CONFIDENCE', '0.8').strip().lower()
FACT_AUTO_CONFIRM_MIN_CONFIDENCE = None if _auto_confirm in ('', 'off', 'none', 'false') else float(_auto_confirm)
# NOTE: since the verification pipeline (apps/facts/verification/), FACT_AUTO_CONFIRM_MIN_CONFIDENCE no longer
# confirms anything on its own: AI confidence alone never confirms a fact. Kept so existing env files still load.

# Fact verification and safe automation (apps/facts/verification/policy.py).
# 'shadow' (default): every fact is verified and the policy records what it WOULD do; no fact changes.
# 'enforce': verified facts the policy allows are confirmed by the system account. Switch only after
# `python manage.py fact_verification_report --shadow` shows the rules agree with reviewers.
FACT_VERIFICATION_MODE = os.getenv('FACT_VERIFICATION_MODE', 'shadow').strip().lower()
# Risk by data type ('low' | 'medium' | 'high'), field-key overrides, and what each risk may automate.
FACT_RISK_BY_TYPE = {}
FACT_RISK_BY_FIELD = {}
FACT_AUTOMATION_POLICY = {
    'low': {'automate': True, 'allow_precedent': True},
    'medium': {'automate': True, 'allow_precedent': True},
    'high': {'automate': False, 'allow_precedent': True},
}
# Facts the extractor rated below this always go to a person (this only adds review; never confirms).
FACT_REVIEW_BELOW_CONFIDENCE = float(os.getenv('FACT_REVIEW_BELOW_CONFIDENCE', os.getenv(
    'GAP_LOW_CONFIDENCE_THRESHOLD', 0.7)))
# Extra allowed ranges for particular fields: {field_key regex: [min, max]} (None = open).
FACT_VALIDATION_RANGES = {r'percent|pct|ratio_pct': [0, 100]}

# apps.extraction.services.pdf_reader: a page with fewer than this many
# extractable characters (or mostly non-letter garbage) is sent to OCR; if
# OCR can't read it either, it's flagged rather than treated as empty.
PDF_MIN_TEXT_CHARS_PER_PAGE = int(os.getenv('PDF_MIN_TEXT_CHARS_PER_PAGE', 40))

# OCR for scanned / image-only PDF pages (apps.extraction.services.paddle_ocr).
# OCR_PROVIDER: 'paddle' (PaddleOCR, models download on first use) or 'none'.
# OCR_DPI: resolution pages are rendered at before OCR -- higher reads small
# print better but is slower. OCR_MIN_CONFIDENCE: recognised lines below
# this score are dropped rather than risk a misread number becoming a fact.
# The test suite never loads real OCR models (slow, downloaded on first use)
# unless OCR_PROVIDER is set explicitly; OCR tests inject a fake provider.
_RUNNING_TESTS = len(sys.argv) > 1 and sys.argv[1] == 'test'
OCR_PROVIDER = os.getenv('OCR_PROVIDER', 'none' if _RUNNING_TESTS else 'paddle').strip().lower()
OCR_LANG = os.getenv('OCR_LANG', 'en')
OCR_DPI = int(os.getenv('OCR_DPI', 200))
OCR_MIN_CONFIDENCE = float(os.getenv('OCR_MIN_CONFIDENCE', 0.5))
# OCR_RETRY_DPI: a page whose first OCR pass (at OCR_DPI) finds no readable text is rendered again at this
# resolution and read once more (small or faint print). 0 = no second pass.
OCR_RETRY_DPI = int(os.getenv('OCR_RETRY_DPI', 300))
# PDF_TABLE_EXTRACTION: keep a text-layer table's header and rows together (PyMuPDF find_tables), rendered as
# "column: value" rows with the table and page number, instead of loose cell lines.
PDF_TABLE_EXTRACTION = os.getenv('PDF_TABLE_EXTRACTION', 'true').strip().lower() in ('1', 'true', 'yes')
# OCR_ENABLE_MKLDNN: PaddlePaddle's oneDNN CPU acceleration -- roughly 4-5x
# faster, but broken in paddlepaddle 3.3.x on Windows (pinned <3.3 in
# requirements); set false if your paddlepaddle version crashes with it.
# OCR_DET_MODEL: text-detection model. The mobile one reads document pages as
# well as the server one in practice and is about twice as fast on CPU; set
# 'PP-OCRv5_server_det' for hard scans, or blank for PaddleOCR's default.
OCR_ENABLE_MKLDNN = os.getenv('OCR_ENABLE_MKLDNN', 'true').strip().lower() in ('1', 'true', 'yes')
OCR_DET_MODEL = os.getenv('OCR_DET_MODEL', 'PP-OCRv5_mobile_det').strip()

# apps.extraction.services.openai_fact_extractor: a document's pages are
# grouped into chunks (never splitting a page) capped at this many
# characters each, so one document never blows past the model's input
# limit in a single request. MAX_CHUNKS is a hard safety cap on how many
# chunks (i.e. OpenAI calls) one document can trigger -- an extra-large
# document logs a warning and only its first MAX_CHUNKS chunks are
# processed, rather than an unbounded number of API calls.
OPENAI_FACT_EXTRACTION_MAX_CHUNK_CHARS = int(os.getenv('OPENAI_FACT_EXTRACTION_MAX_CHUNK_CHARS', 12000))
# Inside an extraction job this caps the NEW AI chunk calls of one attempt, not the document: past it the job
# saves its chunks and continues in a follow-up attempt (services/chunk_store.py), so every chunk is read.
# 0 = no cap. EXTRACTION_MAX_CONTINUATIONS bounds how many follow-ups one run may take.
OPENAI_FACT_EXTRACTION_MAX_CHUNKS = int(os.getenv('OPENAI_FACT_EXTRACTION_MAX_CHUNKS', 20))
EXTRACTION_MAX_CONTINUATIONS = int(os.getenv('EXTRACTION_MAX_CONTINUATIONS', 100))
EXTRACTION_CONTINUE_DELAY_SECONDS = int(os.getenv('EXTRACTION_CONTINUE_DELAY_SECONDS', 2))

# apps.extraction.services.conflict_checker: safety cap on how many
# candidate (fact, fact) pairs one document's processing can send to OpenAI
# for a semantic conflict verdict -- bounds API calls if one field_key ends
# up with an unusually large number of disagreeing documents.
GAP_CONFLICT_CHECK_MAX_PAIRS = int(os.getenv('GAP_CONFLICT_CHECK_MAX_PAIRS', 10))

# Set to true to enable apps.extraction's opt-in integration test, which
# uses a real PDF and makes a real call to the OpenAI API (spending real
# quota) instead of a mocked one. Off by default; never enabled by the
# normal `manage.py test` run in CI or local development.
RUN_OPENAI_INTEGRATION_TESTS = os.getenv('RUN_OPENAI_INTEGRATION_TESTS', 'false').lower() == 'true'

# apps.extraction retry policy: recoverable failures get this many retries,
# with exponential backoff (attempt N waits BACKOFF * 2^(N-1) seconds)
# before the job is marked permanently failed.
EXTRACTION_MAX_RETRIES = int(os.getenv('EXTRACTION_MAX_RETRIES', 3))
EXTRACTION_RETRY_BACKOFF_SECONDS = int(os.getenv('EXTRACTION_RETRY_BACKOFF_SECONDS', 30))
# Backoff gets 50-100% jitter and is capped here; a provider's Retry-After is respected (up to the cap).
EXTRACTION_RETRY_MAX_BACKOFF_SECONDS = int(os.getenv('EXTRACTION_RETRY_MAX_BACKOFF_SECONDS', 15 * 60))

# Provider-aware AI calls (apps/extraction/services/rate_limit.py):
# AI_SDK_MAX_RETRIES: the provider SDK's own quick retries per request (they honour Retry-After).
# AI_RATE_LIMIT_RPM / AI_RATE_LIMIT_TPM: requests / tokens per minute shared by every worker, per provider + model
#   + API key (0 = no limit). Set them a little under the account's real limits.
# AI_RATE_LIMIT_MAX_WAIT_SECONDS: a request waits this long for a free window, then the job is retried later.
# AI_RETRY_MAX_DELAY_SECONDS: the longest Retry-After pause shared with other workers.
# AI_QUOTA_EXHAUSTED_HOLD_SECONDS: after "out of quota / credit", other requests with that key fail at once
#   (no call, no retry loop) for this long, or until `manage.py ai_router_reactivate` clears it.
AI_SDK_MAX_RETRIES = int(os.getenv('AI_SDK_MAX_RETRIES', 2))
# Repeatable extraction: the same document gives the same facts. AI_TEMPERATURE 0 = always the most likely answer;
# AI_SEED fixes what randomness is left (OpenAI-compatible endpoints only -- Ollama, vLLM, OpenAI; Anthropic has no
# seed). Empty AI_TEMPERATURE / AI_SEED = the provider's own default.
AI_TEMPERATURE = float(os.getenv('AI_TEMPERATURE', '0')) if os.getenv('AI_TEMPERATURE', '0').strip() else None
AI_SEED = int(os.getenv('AI_SEED', '42')) if os.getenv('AI_SEED', '42').strip() else None
AI_RATE_LIMIT_ENABLED = (os.getenv('AI_RATE_LIMIT_ENABLED', 'false' if _RUNNING_TESTS else 'true').lower()
                         in ('1', 'true', 'yes'))
AI_RATE_LIMIT_RPM = int(os.getenv('AI_RATE_LIMIT_RPM', 0))
AI_RATE_LIMIT_TPM = int(os.getenv('AI_RATE_LIMIT_TPM', 0))
AI_RATE_LIMIT_MAX_WAIT_SECONDS = int(os.getenv('AI_RATE_LIMIT_MAX_WAIT_SECONDS', 90))
AI_RATE_LIMIT_OUTPUT_ESTIMATE = int(os.getenv('AI_RATE_LIMIT_OUTPUT_ESTIMATE', 2000))
AI_RETRY_MAX_DELAY_SECONDS = int(os.getenv('AI_RETRY_MAX_DELAY_SECONDS', 300))
AI_QUOTA_EXHAUSTED_HOLD_SECONDS = int(os.getenv('AI_QUOTA_EXHAUSTED_HOLD_SECONDS', 30 * 60))

# Page-level vision fallback (apps/extraction/services/vision_fallback.py):
# When local text extraction and OCR fail/return no readable text on a page, render only that page
# and send its image to the configured AI provider if the model supports vision.
AI_VISION_ENABLED = os.getenv('AI_VISION_ENABLED', 'true').lower() in ('1', 'true', 'yes')
AI_VISION_MODELS = [m.strip().lower() for m in os.getenv('AI_VISION_MODELS', '').split(',') if m.strip()]
AI_VISION_DPI = int(os.getenv('AI_VISION_DPI', '150'))

# apps.documents's Google Drive Link data source (Screen 2 "Upload Data
# Pack"): a single server-side Drive REST v3 API key -- no OAuth client, no
# per-institution token storage. Institutions must share their Drive folder
# as "Anyone with the link -- Viewer" for this key to be able to list/
# download its contents. Deliberately left unset-safe here, same reasoning
# as AI_API_KEY above -- the Celery task raises a clear, job-level
# error_message if it's missing when actually used.
GOOGLE_DRIVE_API_KEY = os.getenv('GOOGLE_DRIVE_API_KEY', '')

# Hard cap on how many files one drive-import job will list/consider, so a
# huge or misconfigured folder can't make one job page through Drive
# indefinitely. Subfolders are scanned recursively (breadth-first);
# GOOGLE_DRIVE_IMPORT_MAX_FOLDERS separately caps how many folders total get
# walked, guarding against a deeply-nested or unexpectedly wide tree.
GOOGLE_DRIVE_IMPORT_MAX_FILES = int(os.getenv('GOOGLE_DRIVE_IMPORT_MAX_FILES', 200))
GOOGLE_DRIVE_IMPORT_MAX_FOLDERS = int(os.getenv('GOOGLE_DRIVE_IMPORT_MAX_FOLDERS', 200))

# Retry policy for transient Drive API failures (network hiccups, 5xx),
# mirrors EXTRACTION_MAX_RETRIES/EXTRACTION_RETRY_BACKOFF_SECONDS but kept as
# its own knob since it's an unrelated task/queue.
# How many Drive requests may be in flight at once -- folders during the
# scan, files during the download. Both phases were strictly serial, which is
# what made a large shared folder take minutes: the wall clock was the SUM of
# every round trip. Kept modest because this runs against a single API key
# whose quota is shared by every import.
GOOGLE_DRIVE_IMPORT_CONCURRENCY = int(os.getenv('GOOGLE_DRIVE_IMPORT_CONCURRENCY', 6))
GOOGLE_DRIVE_IMPORT_MAX_RETRIES = int(os.getenv('GOOGLE_DRIVE_IMPORT_MAX_RETRIES', 3))
GOOGLE_DRIVE_IMPORT_RETRY_BACKOFF_SECONDS = int(os.getenv('GOOGLE_DRIVE_IMPORT_RETRY_BACKOFF_SECONDS', 15))

def _int_env(name, default):
    """Read an int setting, tolerating a present-but-empty variable.

    `.env` files routinely carry `KEY=` for "leave this unset", and a bare
    int('') raises ValueError at import time -- which takes the whole
    application down at startup rather than degrading. Blank means "use the
    default", which is what an empty line in a .env is meant to say.
    """
    raw = (os.getenv(name) or '').strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Vector store (apps.vector_store) -- semantic retrieval over college document
# content, so a future benchmarking criterion can pull the relevant evidence
# and hand it to an LLM.
#
# PostgreSQL stays the source of truth for every structured record. Pinecone
# holds only embeddings of document text plus the metadata needed to filter and
# cite them; nothing here replaces or duplicates a Django model.
#
# Entirely optional. When PINECONE_API_KEY / PINECONE_INDEX_NAME (or an
# embedding key) are unset, `apps.vector_store.services.indexer.is_enabled()`
# is False: no Celery task is queued, no row is written, and document upload,
# extraction, scoring and reports behave exactly as they did before this app
# existed. The API endpoints answer 503 with a clear reason rather than 500.
# ---------------------------------------------------------------------------
PINECONE_API_KEY = os.getenv('PINECONE_API_KEY', '')
PINECONE_INDEX_NAME = os.getenv('PINECONE_INDEX_NAME', '')
# Used only when creating the index (see docs/VECTOR_STORE.md); the SDK reads
# the index by name at runtime, so these two are documentation for operators
# rather than something the client sends on every call.
PINECONE_CLOUD = os.getenv('PINECONE_CLOUD', 'aws')
PINECONE_REGION = os.getenv('PINECONE_REGION', 'us-east-1')
# Optional. Institution isolation is enforced by metadata filtering (see
# apps.vector_store.services.search), so a namespace is not required; it is
# here for operators who want one index shared across environments.
PINECONE_NAMESPACE = os.getenv('PINECONE_NAMESPACE', '')

# How vectors get their embeddings:
#   integrated -- the Pinecone index embeds server-side (an index created with
#                 an `embed` config, e.g. llama-text-embed-v2). No embedding
#                 key or model is needed here; Pinecone owns both.
#   manual     -- this app embeds via EMBEDDING_* below and upserts raw vectors.
#   auto       -- (default) ask the index which it is, once per process, and
#                 cache it. Costs one describe_index call the first time a
#                 store is built, never in the request path.
# The two use different Pinecone APIs (upsert_records/search vs upsert/query),
# which is why this is a mode and not just a different embedding provider.
PINECONE_EMBEDDING_MODE = os.getenv('PINECONE_EMBEDDING_MODE', 'auto')

# Embeddings. Deliberately separate from the extraction AI settings above:
# Anthropic publishes no embedding endpoint, so a deployment running Claude for
# extraction still needs an OpenAI-compatible key here. Falls back to
# OPENAI_API_KEY / AI_API_KEY when those are usable -- see
# apps.vector_store.services.embeddings._resolve_api_key.
EMBEDDING_API_KEY = os.getenv('EMBEDDING_API_KEY', '')
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
# Blank means "derive from the model" (see embeddings.KNOWN_MODEL_DIMENSIONS).
# Set it only for a model this app does not know the width of.
EMBEDDING_DIMENSIONS = _int_env('EMBEDDING_DIMENSIONS', 0) or None
EMBEDDING_BASE_URL = os.getenv('EMBEDDING_BASE_URL', '')

# Chunking. A chunk never spans a page (page number is the citation this
# platform promises) and never splits a sentence unless one sentence is longer
# than the whole budget. Overlap must stay below the max or chunking cannot
# terminate -- apps.vector_store.services.chunking enforces that.
VECTOR_CHUNK_MAX_CHARS = _int_env('VECTOR_CHUNK_MAX_CHARS', 1200)
VECTOR_CHUNK_OVERLAP_CHARS = _int_env('VECTOR_CHUNK_OVERLAP_CHARS', 150)
# Below this a chunk is page furniture (a header, a page number) that would
# only compete with real evidence at search time.
VECTOR_CHUNK_MIN_CHARS = _int_env('VECTOR_CHUNK_MIN_CHARS', 40)

# Indexing retry policy, mirroring EXTRACTION_MAX_RETRIES above: recoverable
# failures back off exponentially, permanent ones fail the row immediately.
VECTOR_INDEX_MAX_RETRIES = _int_env('VECTOR_INDEX_MAX_RETRIES', 3)
VECTOR_INDEX_RETRY_BACKOFF_SECONDS = _int_env('VECTOR_INDEX_RETRY_BACKOFF_SECONDS', 20)

VECTOR_SEARCH_DEFAULT_TOP_K = _int_env('VECTOR_SEARCH_DEFAULT_TOP_K', 5)
# Hard ceiling, so a caller cannot ask for an unbounded result set.
VECTOR_SEARCH_MAX_TOP_K = _int_env('VECTOR_SEARCH_MAX_TOP_K', 50)

# Logging: without this, module-level `logging.getLogger(__name__)` calls in
# apps.* (extraction's pipeline/task logging in particular) fall back to
# Python's silent last-resort handler and never appear anywhere.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} {levelname} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'apps': {
            'handlers': ['console'],
            'level': os.getenv('APP_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': os.getenv('CELERY_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}

# Production: email ADMINS the traceback of every server error (HTTP 500).
if not DEBUG and ADMINS and EMAIL_HOST_USER:
    LOGGING['handlers']['mail_admins'] = {
        'class': 'django.utils.log.AdminEmailHandler', 'level': 'ERROR', 'include_html': False,
    }
    LOGGING['loggers']['django.request'] = {
        'handlers': ['console', 'mail_admins'], 'level': 'ERROR', 'propagate': False,
    }

# Production hardening -- applied automatically whenever DEBUG is off, so
# there's no separate production settings module to remember to point at.
# Set DEBUG=False (the default) in .env for any real deployment.
if not DEBUG:
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True') == 'True'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # The container healthcheck calls this over plain HTTP from inside the container.
    SECURE_REDIRECT_EXEMPT = [r'^api/v1/health$']


# Slow-request diagnostics (config/request_diagnostics.py): log an API request slower than this, or running
# more database queries than this.
API_SLOW_REQUEST_MS = int(os.getenv('API_SLOW_REQUEST_MS', 1000))
API_SLOW_REQUEST_QUERIES = int(os.getenv('API_SLOW_REQUEST_QUERIES', 100))

# AI-QIF tags the rules leave for an expert get an AI second opinion (apps/facts/aiqif_tagging.ai_check_pending):
# accepted when the check agrees with at least this confidence; at most this many checks per document.
# Off by default under `manage.py test` (no unmocked AI call); the AI-check tests switch it on.
AIQIF_AI_CHECK_ENABLED = os.getenv(
    'AIQIF_AI_CHECK_ENABLED', 'false' if len(sys.argv) > 1 and sys.argv[1] == 'test' else 'true',
).strip().lower() not in ('', '0', 'false', 'off')
AIQIF_AI_CHECK_MIN_CONFIDENCE = float(os.getenv('AIQIF_AI_CHECK_MIN_CONFIDENCE', 0.8))
AIQIF_AI_CHECK_MAX_PER_DOCUMENT = int(os.getenv('AIQIF_AI_CHECK_MAX_PER_DOCUMENT', 40))
