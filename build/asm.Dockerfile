FROM gcc:9

RUN apt-get update && apt-get install nasm -y --no-install-recommends && rm -rf /var/lib/apt/lists/*

COPY run_entrypoint.sh /usr/bin/

ENTRYPOINT ["run_entrypoint.sh"]
CMD ["./exec_input"]
