FROM gcc:9

RUN apt update && apt install nasm -y

COPY run_entrypoint.sh /usr/bin/

ENTRYPOINT ["run_entrypoint.sh"]
CMD ["./exec_input"]
