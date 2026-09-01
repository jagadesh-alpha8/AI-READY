import os
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
    'apps.reports',
    'apps.dashboard',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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
}

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
# No periodic/scheduled tasks exist in this project (every task is
# triggered on-demand from an API call), so Celery Beat is not configured.
# Add CELERY_BEAT_SCHEDULE here if a recurring job is ever introduced.

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
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_EXTRACTION_MODEL = os.getenv('OPENAI_EXTRACTION_MODEL', '')

# apps.extraction.services.openai_classifier: how many pages of a document's
# extracted text get sampled and sent to OpenAI for classification.
OPENAI_CLASSIFICATION_SAMPLE_PAGES = int(os.getenv('OPENAI_CLASSIFICATION_SAMPLE_PAGES', 3))

# apps.extraction.services.pdf_reader: a page with fewer than this many
# extractable characters is flagged as requiring OCR rather than treated as
# genuinely (and silently) empty.
PDF_MIN_TEXT_CHARS_PER_PAGE = int(os.getenv('PDF_MIN_TEXT_CHARS_PER_PAGE', 40))

# apps.extraction.services.openai_fact_extractor: a document's pages are
# grouped into chunks (never splitting a page) capped at this many
# characters each, so one document never blows past the model's input
# limit in a single request. MAX_CHUNKS is a hard safety cap on how many
# chunks (i.e. OpenAI calls) one document can trigger -- an extra-large
# document logs a warning and only its first MAX_CHUNKS chunks are
# processed, rather than an unbounded number of API calls.
OPENAI_FACT_EXTRACTION_MAX_CHUNK_CHARS = int(os.getenv('OPENAI_FACT_EXTRACTION_MAX_CHUNK_CHARS', 12000))
OPENAI_FACT_EXTRACTION_MAX_CHUNKS = int(os.getenv('OPENAI_FACT_EXTRACTION_MAX_CHUNKS', 20))

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
GOOGLE_DRIVE_IMPORT_MAX_RETRIES = int(os.getenv('GOOGLE_DRIVE_IMPORT_MAX_RETRIES', 3))
GOOGLE_DRIVE_IMPORT_RETRY_BACKOFF_SECONDS = int(os.getenv('GOOGLE_DRIVE_IMPORT_RETRY_BACKOFF_SECONDS', 15))

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
