from bi_governance_lab.ui import streamlit_app


def test_streamlit_app_exposes_expected_pages():
    expected_renderers = [
        streamlit_app.render_executive_dashboard,
        streamlit_app.render_asset_catalog,
        streamlit_app.render_governance_findings,
        streamlit_app.render_accessibility_review,
        streamlit_app.render_style_guide_compliance,
        streamlit_app.render_refresh_health,
        streamlit_app.render_workspace_explorer,
    ]

    labels = [
        streamlit_app.NavigationPage(renderer.__name__, renderer).label
        for renderer in expected_renderers
    ]

    assert labels == [
        "render_executive_dashboard",
        "render_asset_catalog",
        "render_governance_findings",
        "render_accessibility_review",
        "render_style_guide_compliance",
        "render_refresh_health",
        "render_workspace_explorer",
    ]
    assert streamlit_app.PAGE_TITLE == "BI Governance Lab"
