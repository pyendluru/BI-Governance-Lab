from bi_governance_lab.config import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.app_name == "BI Governance Lab"
    assert settings.database_url.startswith("sqlite")
