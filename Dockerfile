FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159 AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt requirements-test.txt ./
RUN pip install -r requirements.txt

FROM base AS checks
RUN pip install -r requirements-test.txt
COPY backend/ ./backend/
COPY tests/test_backend.py ./tests/test_backend.py
RUN python -m unittest discover -s tests -p 'test_*.py' -v

FROM base AS app
COPY --from=checks /app/backend/ ./backend/
COPY index.html styles.css app.js ./static/
COPY docs/ ./static/docs/
COPY examples/ ./static/examples/
RUN useradd --uid 10001 --create-home app
USER app
EXPOSE 8080
HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=2)" || exit 1
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
