from uuid import uuid4
import pytest
from test_explain_endpoint import db, client, _usuario, _articulo, _pasos, _token, _proyecto
from app.models import UserRole


@pytest.mark.asyncio
async def test_selects_exact_execution_and_keeps_recovered_errors(db, client):
    owner = await _usuario("history@test.com")
    article = await _articulo(owner.id)
    await _pasos(article.id, [
        dict(agent_name="investigador", step_index=0, output_text="old", tokens_in=10),
        dict(agent_name="redactor", step_index=1, status="failed", error_message="retry"),
        dict(agent_name="redactor", step_index=1, status="completed", output_text="old", tokens_out=20),
        dict(agent_name="investigador", step_index=0, output_text="new", tokens_in=99),
    ])
    async with client as ac:
        headers = {"Authorization": f"Bearer {await _token(ac, owner.email)}"}
        base = f"/api/v1/agents/{article.id}/history"
        response = await ac.get(base, headers=headers)
        assert response.status_code == 200, response.text
        executions = response.json()["executions"]
        assert [e["run_number"] for e in executions] == [2, 1]
        old = await ac.get(f"{base}/{executions[1]['id']}", headers=headers)
        assert old.status_code == 200, old.text
        data = old.json()
        assert len(data["steps"]) == 3
        assert data["execution"]["status"] == "completed"
        assert data["execution"]["recovered_failures"] == 1
        assert data["execution"]["tokens_in"] == 10
        assert data["steps"][1]["error_message"] == "retry"
        assert data["integrity"]["status"] == "sin_cadena"
        assert (await ac.get(f"{base}/{uuid4()}", headers=headers)).status_code == 404
        foreign = await _articulo(owner.id)
        assert (await ac.get(f"/api/v1/agents/{foreign.id}/history/{executions[1]['id']}", headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_empty_and_permissions(db, client):
    owner = await _usuario("history-owner@test.com")
    outsider = await _usuario("history-outsider@test.com")
    article = await _articulo(owner.id)
    async with client as ac:
        base = f"/api/v1/agents/{article.id}/history"
        assert (await ac.get(base)).status_code in (401,403)
        owner_headers = {"Authorization": f"Bearer {await _token(ac, owner.email)}"}
        empty = await ac.get(base, headers=owner_headers)
        assert empty.json()["executions"] == []
        outsider_headers = {"Authorization": f"Bearer {await _token(ac, outsider.email)}"}
        assert (await ac.get(base, headers=outsider_headers)).status_code == 403
        assert (await ac.get(f"{base}/{uuid4()}", headers=outsider_headers)).status_code == 403


@pytest.mark.asyncio
async def test_active_project_is_checked_for_list_and_detail(db, client):
    owner = await _usuario("history-project@test.com", role=UserRole.ADMIN)
    project = await _proyecto("Own", owner_id=owner.id)
    other = await _proyecto("Other", owner_id=owner.id)
    article = await _articulo(owner.id, project.id)
    async with client as ac:
        headers = {"Authorization": f"Bearer {await _token(ac, owner.email)}", "X-Project-Id": str(other.id)}
        base = f"/api/v1/agents/{article.id}/history"
        assert (await ac.get(base, headers=headers)).status_code == 404
        assert (await ac.get(f"{base}/{uuid4()}", headers=headers)).status_code == 404
