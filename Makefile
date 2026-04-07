.PHONY: help up down down-clean restart reload build logs logs-backend logs-frontend ps db-migrate db-upgrade db-shell shell-backend shell-frontend fresh

help:                          ## Zeigt diese Hilfe
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Docker Compose Commands ---

up:                            ## Startet alle Services (detached)
	docker compose up -d

down:                          ## Stoppt alle Services (Volumes bleiben erhalten)
	docker compose down

down-clean:                    ## Stoppt alle Services UND loescht Volumes (DB wird geloescht!)
	docker compose down -v

restart:                       ## Kompletter Restart: down + build + up
	docker compose down
	docker compose build --no-cache
	docker compose up -d

reload:                        ## Schneller Reload: nur Container neu starten (kein Rebuild)
	docker compose restart backend frontend

build:                         ## Nur bauen ohne starten
	docker compose build

logs:                          ## Logs aller Services (follow)
	docker compose logs -f

logs-backend:                  ## Logs nur Backend
	docker compose logs -f backend

logs-frontend:                 ## Logs nur Frontend
	docker compose logs -f frontend

ps:                            ## Status aller Services
	docker compose ps

# --- Database ---

db-migrate:                    ## Neue Alembic Migration erstellen (MSG=... angeben)
	docker compose exec backend alembic revision --autogenerate -m "$(MSG)"

db-upgrade:                    ## Alembic Migrations ausfuehren
	docker compose exec backend alembic upgrade head

db-shell:                      ## PostgreSQL Shell oeffnen
	docker compose exec postgres psql -U recruiterai -d recruiterai

# --- Development ---

shell-backend:                 ## Shell im Backend Container
	docker compose exec backend bash

shell-frontend:                ## Shell im Frontend Container
	docker compose exec frontend sh

# --- Shortcuts ---

fresh:                         ## Komplett neu: Volumes loeschen + rebuild + migrate
	docker compose down -v
	docker compose build --no-cache
	docker compose up -d
	sleep 5
	docker compose exec backend alembic upgrade head
