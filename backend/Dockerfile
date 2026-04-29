FROM public.ecr.aws/docker/library/python:3.13-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd -r appuser && useradd -r -g appuser appuser

COPY . .

ENV LOGLEVEL=INFO
ENV HOST=0.0.0.0
ENV PORT=8080
ENV AWS_DEFAULT_REGION=us-east-1
ENV PYTHONPATH=/app
ENV ENABLE_STRANDS_AGENT=true

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "-u", "server.py"]
