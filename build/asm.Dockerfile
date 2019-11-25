FROM iomirea/run-lang-cpp

RUN apt-get update \
    && apt-get install nasm -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
