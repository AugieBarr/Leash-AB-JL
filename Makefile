# Leash — one-command entrypoints. See docs/RUNBOOK.md for the full live-run guide.
# Everything runs through uv (https://docs.astral.sh/uv/); `make install` first.

.PHONY: help install test lint proof demo verify viewer control-demo tamper-demo \
        juice-up juice-down boot-check seed live clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Sync the dev environment (runtime + test deps)
	uv sync --extra dev

# ---- Target-free proof (NO Docker, NO Band, NO API key) ----------------------
# This is what a reviewer can run in a bare checkout to verify the governance,
# crypto, scope, gate/kill-switch, and scale claims — none of it needs a target.
proof: ## Verify every claim that needs no live target (tests + lint + 1000-job scale)
	uv run ruff check .
	uv run pytest -q
	uv run python -m scale_test.worker_fanout_bench --workers 1000 --cap 16

test: ## Run the full governance test suite
	uv run pytest -q

lint: ## Lint with ruff
	uv run ruff check .

# ---- Deterministic governed demo (needs Docker/Juice Shop; NO Band, NO LLM) --
demo: juice-up ## Run the full governed pipeline against Juice Shop, then verify the sealed bundle
	uv run python scripts/offline_demo.py
	uv run python -m governance.verify engagements/offline-demo/offline-demo_bundle.tar.gz

verify: ## Re-verify the last sealed offline-demo bundle (offline, public key only)
	uv run python -m governance.verify engagements/offline-demo/offline-demo_bundle.tar.gz

viewer: ## Serve the live Control Center on http://localhost:8089
	uv run python -m viewer.viewer

control-demo: ## Paced, web-driven approval-gate demo (run `make viewer` in another shell)
	uv run python scripts/control_demo.py

tamper-demo: ## Prove the audit trail cannot be rewritten (flips one signed event)
	uv run python scripts/tamper_demo.py

juice-up: ## Start the authorized lab target (OWASP Juice Shop) on :3000
	docker compose up -d juice-shop

juice-down: ## Stop the lab target
	docker compose down

# ---- Live Band swarm (needs ANTHROPIC_API_KEY + the 8 agents registered) -----
boot-check: ## Connect all 8 Band agents, print N/8, exit (no Anthropic key needed)
	uv run python -m swarm.launcher --boot-check

seed: ## Create the Band case room and add the roster
	uv run python -m swarm.seed --target localhost:3000

live: juice-up ## Run the live LLM-driven swarm (needs .env + agent_config.yaml). Start `make viewer` first.
	uv run python -m swarm.launcher --engagement-id demo-01

clean: ## Remove generated engagement artifacts (gitignored runtime output)
	rm -rf engagements/*/ 2>/dev/null || true
