SHELL := /bin/bash

.PHONY: train-setup train-cpu

# Convenience Makefile for running from backend/

train-setup:
	@echo "\n[+] Setting up local training environment (venv + deps)..."; \
	bash scripts/setup_training_env.sh

train-cpu:
	@echo "\n[+] Running local CPU training..."; \
	bash run_training.sh

