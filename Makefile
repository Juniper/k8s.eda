EDA_COLLECTION_ROOT := .

# Get all .py files in the EDA_COLLECTION_ROOT directory
PY_FILES := $(shell find $(EDA_COLLECTION_ROOT) -name *.py)

VERSION := $(shell sed -n '/^version: / s,.*"\(.*\)"$$,\1,p' $(EDA_COLLECTION_ROOT)/galaxy.yml)

PY_VERSION := $(shell cat .python-version)

EDA_COLLECTION = junipernetworks-eda-$(VERSION).tar.gz

.PHONY: setup build release-build install clean clean-pipenv pipenv docs

# OS-specific settings
OS := $(shell uname -s)
ifeq ($(OS),Darwin)
PYENV_INSTALL_PREFIX := PYTHON_CONFIGURE_OPTS=--enable-framework
else
# Unix
export LDFLAGS := -Wl,-rpath,$(shell brew --prefix openssl)/lib
export CPPFLAGS := -I$(shell brew --prefix openssl)/include
export CONFIGURE_OPTS := --with-openssl=$(shell brew --prefix openssl)
endif

# By default use .venv in the current directory
export PIPENV_VENV_IN_PROJECT=1

setup: clean-pipenv
	pyenv uninstall --force $(PY_VERSION)
	rm -rf $(HOME)/.pyenv/versions/$(PY_VERSION)
	$(PYENV_INSTALL_PREFIX) pyenv install --force $(PY_VERSION)
	pip install pipenv pre-commit
	$(MAKE) pipenv
	pre-commit install

define install_collection_if_missing
	pipenv run ansible-doc $(1) &>/dev/null || pipenv run ansible-galaxy collection install --ignore-certs --force $(1)
endef

pipenv:
	pipenv --help &>/dev/null || pip install pipenv
	pipenv install --dev

release-build:
	rm -f $(EDA_COLLECTION_ROOT)/.eda-collection
	make clean-pipenv
	pipenv install
	make build

build: $(EDA_COLLECTION_ROOT)/.eda-collection

$(EDA_COLLECTION_ROOT)/.eda-collection: $(EDA_COLLECTION_ROOT)/requirements.txt $(EDA_COLLECTION_ROOT)/galaxy.yml  $(PY_FILES)
	rm -f junipernetworks-eda-*.tar.gz
	pipenv run ansible-galaxy collection build $(EDA_COLLECTION_ROOT)
	touch "$@"

$(EDA_COLLECTION_ROOT)/requirements.txt: Pipfile Makefile
	pipenv --rm &>/dev/null || true
	pipenv install
	pipenv run pip freeze > "$@.tmp"
	sed -e 's/==/~=/' "$@.tmp" > "$@"
	rm "$@.tmp"
	pipenv install --dev

install: build
	pipenv run ansible-galaxy collection install --ignore-certs --force $(EDA_COLLECTION)

# Ignore warnings about localhost from ansible-playbook
export ANSIBLE_LOCALHOST_WARNING=False
export ANSIBLE_INVENTORY_UNPARSED_WARNING=False

clean-pipenv:
	pipenv --rm || true
	PIPENV_VENV_IN_PROJECT= pipenv --rm || true
	rm -rf .venv
