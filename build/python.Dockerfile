FROM python:3.7-slim

COPY run_entrypoint.sh /usr/bin/

ENTRYPOINT ["run_entrypoint.sh"]
CMD ["python", "-u", "exec_input"]
