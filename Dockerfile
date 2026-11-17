FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BACKALOR_DATA_DIR=/var/data \
    BACKALOR_REQUIRE_POSTGRES=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 backalor \
    && useradd --uid 10001 --gid backalor --no-create-home backalor
COPY requirements-backend.txt ./
RUN pip install --no-cache-dir -r requirements-backend.txt
COPY backend/ ./backend/
COPY deploy/docker-entrypoint.sh /usr/local/bin/backalor-entrypoint
RUN chmod 755 /usr/local/bin/backalor-entrypoint
EXPOSE 8000
ENTRYPOINT ["backalor-entrypoint"]
CMD ["python", "-m", "backend.serve"]
