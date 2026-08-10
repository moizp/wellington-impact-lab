FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Prebuilt CPU wheel for llama-cpp-python (manylinux2014_x86_64, matches
# Cloud Run's platform) — avoids needing a compiler toolchain in the image
# at all, which keeps the final image smaller and the build much faster.
RUN pip install --no-cache-dir -r requirements.txt \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

COPY app app

# Fetch both fine-tuned GGUFs from their private Hugging Face repos at build
# time, baked into the image — see docs/BUILD_PLAN.md "Validated model
# build/deploy pipeline". HF_TOKEN comes from a Cloud Build substitution
# variable at submit time (see cloudbuild.yaml), never committed here.
ARG HF_TOKEN
RUN mkdir -p models && \
    curl -fL -H "Authorization: Bearer ${HF_TOKEN}" \
    -o models/clarifier-q4km.gguf \
    https://huggingface.co/moiz-hf/impact-lab-clarify-q4km/resolve/main/clarifier-q4km.gguf && \
    curl -fL -H "Authorization: Bearer ${HF_TOKEN}" \
    -o models/triage-q4km.gguf \
    https://huggingface.co/moiz-hf/impact-lab-triage-q4km/resolve/main/triage-q4km.gguf

# Cloud Run injects PORT at runtime and expects the container to listen on it.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
