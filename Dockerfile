FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends espeak-ng ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt

COPY . /app

RUN mkdir -p /app/inference_results /app/artifacts /opt/hf-cache

CMD ["python", "-m", "ela_pipeline.inference.run", "--help"]
