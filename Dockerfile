FROM registry.fedoraproject.org/fedora:28

# Updates and pipenv
RUN dnf update -y && \
    dnf -y install pipenv which make && \
    dnf clean all

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
