run:
	python3 gitrello.py

check:
	pipenv check

install_dev:
	pipenv install -d

pytest:
	pipenv run python3 -m pytest

test: install_dev pytest
