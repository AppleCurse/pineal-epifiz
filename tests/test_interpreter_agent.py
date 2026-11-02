import pytest
from agent_core.agents.interpreter_agent import InterpreterAgent, InterpreterResult

@pytest.mark.asyncio
async def test_interpreter_agent_initialization():
    agent = InterpreterAgent()
    assert agent is not None

@pytest.mark.asyncio
async def test_interpreter_agent_fallback_or_execute():
    agent = InterpreterAgent()
    result = await agent.execute_task("Print hello world in python", auto_run=False)
    assert isinstance(result, InterpreterResult)
    assert result.status in ["empty_response", "response_received", "code_proposed", "execution_unknown", "error"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'messages, expected_status, expected_output',
    [
        ([], 'empty_response', ''),
        ([{'type': 'message', 'content': 'A response'}], 'response_received', 'A response'),
        ([{'type': 'code', 'code': 'print(1)'}], 'code_proposed', ''),
        ([{'type': 'output', 'output': '1'}], 'execution_unknown', '1'),
    ],
)
async def test_provider_response_does_not_claim_execution(monkeypatch, messages, expected_status, expected_output):
    agent = InterpreterAgent()
    monkeypatch.setattr(agent, '_setup_interpreter', lambda **kw: type('Provider', (), {'chat': lambda *a, **k: messages})())
    result = await agent.execute_task('test', auto_run=True)
    assert result.status == expected_status
    assert result.output == expected_output
    assert result.status != 'success'


@pytest.mark.asyncio
async def test_provider_failure_is_error(monkeypatch):
    agent = InterpreterAgent()
    class Broken:
        def chat(self, *_args, **_kwargs):
            raise RuntimeError('provider failure')
    monkeypatch.setattr(agent, '_setup_interpreter', lambda **kw: Broken())
    result = await agent.execute_task('test')
    assert result.status == 'error'
    assert result.error_message


def test_interpreter_api_does_not_log_execution_success(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend import api

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('OPENROUTER_API_KEY', 'sk-or-v1-synthetic-interpreter-test')
    messages = []
    with TestClient(api.app) as client:
        monkeypatch.setenv('ENABLE_INTERPRETER', 'true')
        cid = 'interpreter_no_execution'
        room = api.get_room(cid)
        agent = InterpreterAgent()
        monkeypatch.setattr(agent, '_setup_interpreter', lambda **kw: type('Provider', (), {'chat': lambda *a, **k: []})())
        room['executor'].agents['interpreter'] = agent
        monkeypatch.setattr(api, 'broadcast_log', lambda *args: messages.append(args))
        response = client.post('/api/experimental/interpreter/execute', json={'client_id': cid, 'prompt': 'private test prompt'})
        assert response.status_code == 200, response.text
        assert response.json()['status'] == 'empty_response'
        assert not any('İcra başarıyla tamamlandı' in str(log) for log in messages)
        assert not any('private test prompt' in str(log) for log in messages)
