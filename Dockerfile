# we need to use a debian as dcos-cli's plugins (core/ee) won't work properly under alpine as some subcommands dynamically link glibc.
FROM python:3.9.1-slim-buster

WORKDIR /work
ADD . /work
CMD /bin/bash

RUN apt-get update && apt-get install -y curl git jq

# we may want to revisit https://github.com/pypa/pipenv/issues/3150#issuecomment-522947210 for `pipenv install`-options
RUN pip install pipenv \
      && pipenv install \
      && curl -o /usr/local/bin/dcos https://downloads.dcos.io/cli/testing/binaries/dcos/linux/x86-64/master/dcos \
      && chmod +x /usr/local/bin/dcos
