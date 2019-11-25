FROM python:3.8-alpine3.10

# enables proper stdout flushing
ENV PYTHONUNBUFFERED=yes

# pip optimizations
ENV PIP_NO_CACHE_DIR=yes
ENV PIP_DISABLE_PIP_VERSION_CHECK=yes

WORKDIR /code

# avoid cache invalidation after copying entire directory
COPY requirements.txt .

RUN apk add --no-cache --virtual build-deps \
        gcc \
        make \
        musl-dev \
        git && \
    pip install -r requirements.txt && \
    # aiohttp installation from source until 4.0.0a2 (sentry integration fix: https://github.com/aio-libs/aiohttp/commit/dd85639f0e1855d8921c57db8643b28ffe3f6b25)
    git clone https://github.com/aio-libs/aiohttp --depth 1 --recursive aiohttp && cd aiohttp && \
    git submodule init && \
    make cythonize && \
    pip install . && \
    cd .. && rm -rf aiohttp && \
    apk del build-deps && \
    apk add --no-cache docker-cli

EXPOSE 8080

COPY . .

# RUN addgroup -S iomirea && \
#     adduser -S run-api-public -G iomirea && \
#     chown -R run-api-public:iomirea /code
#
# USER run-api-public

ARG GIT_COMMIT=undefined
ENV GIT_COMMIT=${GIT_COMMIT}
LABEL GIT_COMMIT=${GIT_COMMIT}

ENTRYPOINT ["python", "-m", "runner"]
