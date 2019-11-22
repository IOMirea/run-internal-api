FROM gcc:9

COPY run_entrypoint.sh /usr/bin/

ENTRYPOINT ["run_entrypoint.sh"]
CMD ["./exec_input"]
