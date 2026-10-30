PYTHON ?= python

.PHONY: dev api worker test lint fmt migrate seed eval check screenshots e2e visual

dev:
	$(PYTHON) scripts/tasks.py dev
api:
	$(PYTHON) scripts/tasks.py api
worker:
	$(PYTHON) scripts/tasks.py worker
migrate:
	$(PYTHON) scripts/tasks.py migrate
seed:
	$(PYTHON) scripts/tasks.py seed
test:
	$(PYTHON) scripts/tasks.py test
lint:
	$(PYTHON) scripts/tasks.py lint
fmt:
	$(PYTHON) scripts/tasks.py fmt
eval:
	$(PYTHON) scripts/tasks.py eval $(ARGS)
screenshots:
	npm run screenshots
e2e:
	npm run test:e2e
visual:
	npm run test:visual
check:
	$(PYTHON) scripts/tasks.py check

