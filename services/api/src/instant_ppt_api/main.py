"""FastAPI application factory for the engineering baseline."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Create the API app without business routes during G00."""
    return FastAPI(title="即刻AI-PPT API", version="0.0.0")


app = create_app()

