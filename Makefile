# Makefile to help automate key steps

.DEFAULT_GOAL := help

# A helper script to get short descriptions of each target in the Makefile
define PRINT_HELP_PYSCRIPT
import re, sys

for line in sys.stdin:
	match = re.match(r'^([\$$\(\)a-zA-Z_-]+):.*?## (.*)$$', line)
	if match:
		target, help = match.groups()
		print("%-30s %s" % (target, help))
endef
export PRINT_HELP_PYSCRIPT


help:  ## print short description of each target
	@python3 -c "$$PRINT_HELP_PYSCRIPT" < $(MAKEFILE_LIST)

.PHONY: manuscript
manuscript:  ## build the manuscript (see scripts/create-cmip7-scenariomip-scm-projections-manuscript.sh)
	bash scripts/create-cmip7-scenariomip-scm-projections-manuscript.sh

.PHONY: pre-commit
pre-commit:  ## run pre-commit on all files in the repository
	uv run pre-commit run --all-files

.PHONY: virtual-environment
virtual-environment:  ## update virtual environment, create a new one if it doesn't already exist
	uv sync
	uv run pre-commit install
