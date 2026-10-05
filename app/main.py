from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Escápate API")

    @app.get("/health", include_in_schema=False)
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
