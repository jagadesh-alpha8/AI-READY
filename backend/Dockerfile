FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# libgl1 / libglib2.0-0 / libgomp1: required by OpenCV and PaddlePaddle (OCR of
# scanned PDF pages). Without them PaddleOCR fails to load and scanned pages
# are left flagged "needs OCR".
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# PaddleOCR first, in its own layer (>1 GB). It only changes when
# requirements/ocr.txt changes, so normal deploys reuse it and the server only
# downloads the small layers below. C/C++ headers aren't needed at runtime.
COPY requirements/ocr.txt requirements/ocr.txt
RUN pip install -r requirements/ocr.txt \
    && rm -rf /usr/local/lib/python3.12/site-packages/paddle/include

COPY requirements/ requirements/
RUN pip install -r requirements/production.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
