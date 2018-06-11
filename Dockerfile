FROM registry.fedoraproject.org/fedora-minimal:28

# Updates and pipenv
RUN microdnf update -y && \
    microdnf -y install pipenv which make && \
    microdnf clean all

# Set LANG for pipenv
ENV LANG en_US.UTF-8

# Code and install pipenv
ADD . /code
WORKDIR /code

# Install dependencies
RUN pipenv install --system --deploy

# Use makefile for jobs
ENTRYPOINT ["make"]
CMD ["run"]
