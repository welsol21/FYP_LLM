FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache \
    ELA_MEDIA_DISABLE_RUNTIME_DOWNLOADS=1 \
    ELA_MEDIA_ASR_MODEL=base \
    ELA_MEDIA_ASR_CACHE_DIR=/app/artifacts/models/whisper

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends espeak-ng ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ARG TORCH_VERSION=2.6.0
ARG PRELOAD_RUNTIME_MODELS=0

COPY requirements-docker-cpu.txt /app/requirements-docker-cpu.txt
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple "torch==${TORCH_VERSION}" \
    && pip install -r /app/requirements-docker-cpu.txt

# Fail image build early if ASR dependency is missing.
RUN python -c "import whisper"

# Optional release-mode preload: bundle ASR + translation models in image to avoid runtime downloads for users.
RUN if [ "${PRELOAD_RUNTIME_MODELS}" = "1" ]; then \
      python -c "import whisper; whisper.load_model('base', download_root='/app/artifacts/models/whisper')" && \
      python -c "from transformers import AutoModelForSeq2SeqLM, AutoTokenizer; p='/app/artifacts/models/m2m100_418M'; m='facebook/m2m100_418M'; AutoTokenizer.from_pretrained(m).save_pretrained(p); AutoModelForSeq2SeqLM.from_pretrained(m).save_pretrained(p)"; \
    fi

COPY . /app

RUN mkdir -p /app/inference_results /app/artifacts /opt/hf-cache

CMD ["python", "-m", "ela_pipeline.inference.run", "--help"]
