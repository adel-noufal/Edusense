@echo off
title EduSense PostgreSQL
echo Starting PostgreSQL with Docker...
docker compose up -d postgres
echo.
echo PostgreSQL is running on localhost:5432
echo User: edusense  Password: edusense  Database: edusense
echo.
echo Update backend/.env:
echo EDUSENSE_DATABASE_URL=postgresql+psycopg2://edusense:edusense@localhost:5432/edusense
pause
