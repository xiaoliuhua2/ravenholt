# syntax=docker/dockerfile:1

FROM node:22-alpine AS web-builder

WORKDIR /app/web

# 可选：npm 镜像源。国内网络构建建议传入，例如
#   --build-arg NPM_REGISTRY=https://registry.npmmirror.com
ARG NPM_REGISTRY=
RUN if [ -n "$NPM_REGISTRY" ]; then npm config set registry "$NPM_REGISTRY"; fi

COPY web/package*.json ./
RUN npm ci --no-audit --no-fund

COPY web/ ./
RUN npm run build


FROM python:3.13-slim AS backend

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 可选：pip 镜像源。国内网络构建建议传入，例如
#   --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
# 不传时走 PyPI 官方源（默认行为不变）；同时加长重试与超时，避免连续拉取时被网络抖动打断。
ARG PIP_INDEX_URL=
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir --retries 5 --timeout 60 \
       ${PIP_INDEX_URL:+--index-url} ${PIP_INDEX_URL} -r requirements.txt

COPY app.py config.py database.py logger.py main.py ./
COPY core ./core
COPY handler ./handler
COPY middleware ./middleware
COPY model ./model
COPY router ./router
COPY schema ./schema
COPY service ./service
COPY utils ./utils
COPY strix ./strix
COPY .strix-vendor.json ./
COPY --from=web-builder /app/web/dist-app ./web/dist-app

EXPOSE 8000

CMD ["python", "main.py"]
