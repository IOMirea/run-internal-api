FROM ubuntu:bionic

COPY run_entrypoint.sh /usr/bin/

ENTRYPOINT ["run_entrypoint.sh"]
CMD ["bash", "/input"]
