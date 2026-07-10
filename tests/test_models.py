from bi_governance_lab.models import DataSource, Report, SemanticModel, Workspace


def test_model_relationships(session):
    workspace = Workspace(name="Test Workspace")
    source = DataSource(name="Test Source", source_type="synthetic", connection_summary="none")
    model = SemanticModel(name="Test Model", data_source=source)
    report = Report(name="Test Report", owner="Tester", workspace=workspace, semantic_model=model)
    session.add(report)
    session.commit()

    assert report.workspace.name == "Test Workspace"
    assert report.semantic_model.data_source.name == "Test Source"
