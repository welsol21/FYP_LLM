FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends espeak-ng ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ARG TORCH_VERSION=2.6.0

COPY requirements-docker-cpu.txt /app/requirements-docker-cpu.txt
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple "torch==${TORCH_VERSION}" \
    && pip install -r /app/requirements-docker-cpu.txt

COPY . /app

RUN mkdir -p /app/inference_results /app/artifacts /opt/hf-cache

CMD ["python", "-m", "ela_pipeline.inference.run", "--help"]
