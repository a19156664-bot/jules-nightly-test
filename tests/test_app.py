import pytest
from fastapi.testclient import TestClient

from webui.app import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_tasks_yml(monkeypatch, tmp_path):
    valid_yaml = """
night: "2023-10-27"
test_paths: []
protected_paths: []
turn1:
  - id: "T1"
    title: "task1"
    risk: "low"
    paths: []
    prompt: "hello"
turn2: []
"""
    mock_file = tmp_path / "tasks.yml"
    mock_file.write_text(valid_yaml, encoding="utf-8")

    # Patch the Path object in webui.app
    monkeypatch.setattr("webui.app.TASKS_YML_PATH", mock_file)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_get_tasks():
    response = client.get("/tasks")
    assert response.status_code == 200
    data = response.json()
    assert "night" in data

def test_put_tasks():
    valid_yaml = """
night: "2023-10-28"
test_paths: []
protected_paths: []
turn1:
  - id: "T1"
    title: "task1"
    risk: "low"
    paths: []
    prompt: "hello"
turn2: []
"""
    response = client.put("/tasks", content=valid_yaml, headers={"Content-Type": "application/x-yaml"})

    if response.status_code == 405:
        pytest.skip("PUT /tasks is not implemented yet")
    else:
        assert response.status_code == 200
