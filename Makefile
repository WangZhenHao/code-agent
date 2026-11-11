SHELL := /bin/bash

PNPM ?= pnpm
UV   ?= uv
PY   := apps/api

.DEFAULT_GOAL := help
.PHONY: help install dev dev-web dev-admin server gen-api db-up db-migrate db-revision db-check lint lint-fix build test typecheck fmt fmt-check clean

help: ## 显示所有命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## 安装前后端依赖
	cd apps/web && $(PNPM) install
	cd apps/admin && $(PNPM) install
	cd $(PY) && $(UV) sync

dev: ## 起本地全栈（web + admin）
	$(MAKE) -j2 dev-web dev-admin

dev-web: ## 只起 Next.js
	cd apps/web && $(PNPM) dev

dev-admin: ## 只起 React SPA 管理台
	cd apps/admin && $(PNPM) dev

server: ## 只起 FastAPI（热重载）
	cd $(PY) && $(UV) run code-agent-api

gen-api: ## 从后端 OpenAPI 生成前端 API 类型与 hooks（需先起 dev-api）
	cd apps/web && $(PNPM) gen:api

db-up: ## 起本地 Postgres(5433) + Redis(6380)
	cd $(PY) && docker-compose up -d

db-migrate: ## 应用数据库迁移到最新
	cd $(PY) && $(UV) run alembic upgrade head

db-revision: ## 生成迁移，用法：make db-revision m="add xxx"
	@test -n "$(m)" || { echo '缺少消息，用法：make db-revision m="add xxx"'; exit 1; }
	cd $(PY) && $(UV) run alembic revision --autogenerate -m "$(m)"

db-check: ## 检查模型与数据库是否已同步（漂移检测）
	cd $(PY) && $(UV) run alembic check

lint: ## 前后端 lint（eslint + prettier 一致性 + ruff + mypy）
	cd apps/web && $(PNPM) lint
	cd apps/admin && $(PNPM) lint
	cd apps/web && $(PNPM) format:check
	cd apps/admin && $(PNPM) format:check
	cd $(PY) && $(UV) run ruff check . && $(UV) run ruff format --check . && $(UV) run mypy

lint-fix: ## lint 自动修复（eslint --fix + ruff check --fix）
	cd apps/web && $(PNPM) lint:fix
	cd apps/admin && $(PNPM) lint:fix
	cd $(PY) && $(UV) run ruff check --fix . && $(UV) run ruff format .

typecheck: ## 前端类型检查（tsc）
	cd apps/web && $(PNPM) typecheck
	cd apps/admin && $(PNPM) typecheck

fmt: ## 格式化全部（prettier + ruff format）
	cd apps/web && $(PNPM) format
	cd apps/admin && $(PNPM) format
	cd $(PY) && $(UV) run ruff format . && $(UV) run ruff check --fix .

fmt-check: ## 只检查格式，不改文件
	cd apps/web && $(PNPM) format:check
	cd apps/admin && $(PNPM) format:check
	cd $(PY) && $(UV) run ruff format --check .

test: ## 跑测试（unittest；测试不依赖 pytest）
	cd $(PY) && $(UV) run python -m unittest discover -s tests

build: ## 构建全部
	cd apps/web && $(PNPM) build
	cd apps/admin && $(PNPM) build

clean: ## 清理构建产物
	rm -rf node_modules apps/*/node_modules packages/*/node_modules
	rm -rf apps/web/.next apps/*/dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
