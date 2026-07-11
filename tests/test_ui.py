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


def test_dashboard_queries_have_unambiguous_join_paths(session):
    """Every dashboard query should compile and execute even when its tables are empty."""
    frame_builders = [
        streamlit_app._reports_frame,
        streamlit_app._semantic_models_frame,
        streamlit_app._data_sources_frame,
        streamlit_app._users_frame,
        streamlit_app._workspaces_frame,
        streamlit_app._refresh_health_frame,
    ]

    for build_frame in frame_builders:
        build_frame(session)

    streamlit_app._score_frame(session, "accessibility")
    streamlit_app._permissions_frame(session, workspace_id=1)
