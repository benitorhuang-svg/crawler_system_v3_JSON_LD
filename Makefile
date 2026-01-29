.PHONY: run test init-db clean help audit import-categories
 
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

run: ## Run the main crawler (e.g. PLATFORM=104)
	PYTHONPATH=. uv run main.py $(PLATFORM)

fetch-categories: ## Fetch all raw categories for all platforms
	PYTHONPATH=. uv run python core/categories/fetch_categories_all.py

init-db: ## Initialize Database structure
	PYTHONPATH=. uv run main.py init-db

health-check: ## Run FastAPI health service
	PYTHONPATH=. uv run main.py health

db-status: ## Show Database and crawl health status
	PYTHONPATH=. uv run python test/scripts/inspect_data.py health

audit: ## Run data quality audit (missing rates)
	PYTHONPATH=. uv run python test/scripts/inspect_data.py audit

import-categories: ## Import category mappings from YAML (e.g. FILE=path/to.yaml)
	@if [ -z "$(FILE)" ]; then echo "Usage: make import-categories FILE=path/to.yaml"; exit 1; fi
	PYTHONPATH=. uv run python main.py import $(FILE)

update-schema: ## Apply hotfixes to tb_jobs schema
	PYTHONPATH=. uv run python test/scripts/update_jobs_schema.py

test: ## Run verification scripts
	PYTHONPATH=. uv run python test/scripts/verify_yaml_import.py

worker-celery: ## Start Celery worker
	PYTHONPATH=. uv run celery -A core.celery_app worker --loglevel=info

worker-taskiq: ## Start Taskiq worker
	PYTHONPATH=. uv run taskiq worker core.taskiq_app:broker

scheduler-taskiq: ## Start Taskiq scheduler
	PYTHONPATH=. uv run taskiq scheduler core.taskiq_app:scheduler

clean: ## Remove temporary files
	rm -rf .pytest_cache
	rm -rf __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} +
