FROM node:13-slim

COPY run_entrypoint.sh /usr/bin/

ENTRYPOINT ["run_entrypoint.sh"]
CMD ["node", "exec_input"]
