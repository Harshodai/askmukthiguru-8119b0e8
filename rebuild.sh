#!/bin/bash
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
cd backend
docker compose up -d --build frontend backend
