from instant_ppt_api.main import create_app


def test_application_metadata() -> None:
    app = create_app()
    assert app.title == "即刻AI-PPT API"
    assert app.version == "0.0.0"

