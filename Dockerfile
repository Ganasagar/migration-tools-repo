ARG PYTHON_VERSION
FROM python:$PYTHON_VERSION

RUN pip install pipenv

ENV PYTHONPATH=/dcos-migrate/src
WORKDIR /dcos-migrate
ADD ./ /dcos-migrate
RUN python -m pipenv install --system

ENTRYPOINT ["/dcos-migrate/src/dcos-migrate.py"]
