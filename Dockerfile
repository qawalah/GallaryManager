# Photo Manager for the NAS, built and published by DevStore (see CLAUDE.md).
# The code is baked in; only /config and your photo folders are mounted.
FROM python:3.12-slim
ARG VERSION=dev
LABEL org.opencontainers.image.version=$VERSION

RUN pip install --no-cache-dir pillow==12.3.0 pi-heif==1.4.0

WORKDIR /app
COPY app ./app
COPY core ./core
COPY nas ./nas

ENV PORT=8080 \
    PM_DATA=/config \
    PYTHONUNBUFFERED=1
VOLUME /config
EXPOSE 8080

HEALTHCHECK --interval=2s --timeout=3s --start-period=5s --retries=30 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=2).status == 200 else 1)"

CMD ["sh", "/app/nas/start.sh"]
