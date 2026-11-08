"""SSE streams must end promptly for already-terminal tasks."""

import pytest

from tests.fixtures.factories import create_source, create_task, create_user


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "error", "cancelled"])
async def test_terminal_task_progress_stream_closes(
    client, db_session, auth_headers, status
):
    await create_user(
        db_session, user_id="user-1", email="owner@example.com"
    )
    source = await create_source(db_session)
    task = await create_task(
        db_session, user_id="user-1", source_id=source["id"], status=status
    )

    response = await client.get(
        f"/tasks/{task['id']}/progress", headers=auth_headers
    )

    assert response.status_code == 200
    assert "event: status" in response.text
    assert "event: close" in response.text
    assert f'"status": "{status}"' in response.text
