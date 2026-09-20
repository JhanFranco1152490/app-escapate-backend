# Railway no tiene una fase `release` separada (a diferencia de Heroku): todo lo que
# necesite correr antes de servir tráfico va encadenado en la misma línea `web`.
web: uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
