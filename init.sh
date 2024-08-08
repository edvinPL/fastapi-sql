#!/bin/bash
echo "Setup local db"
docker-compose up -d

echo "Run migrations"
alembic upgrade head
