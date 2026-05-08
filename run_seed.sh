#!/bin/bash
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
cd backend
cat ../seed_admin.py | docker compose exec -T backend python -
