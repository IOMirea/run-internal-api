FROM ubuntu:bionic

COPY run_entrypoint.sh /usr/bin/

RUN apt-get update \
    && apt-get install g++ -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["run_entrypoint.sh"]
CMD ["./exec_input"]
