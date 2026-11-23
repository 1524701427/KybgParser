import asyncio
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

import word_parser.http_api as http_api
from word_parser.http_api import ParseTaskRequest, app, get_parser_service
from word_parser.application.service import ParserService


class FakeParserService:
    def parse(self, file_path: str) -> dict:
        uploaded = Path(file_path)
        assert uploaded.name == "测试报告.pdf"
        assert uploaded.read_bytes() == b"test document"
        return {
            "mapped": {
                "${project_name}": "测试项目",
                "${air_density}": None,
                "${eachTierHeightTurbulenceTableList}": [
                    {
                        "tower_code": "0047#", "height": 90,
                        "wind_speed_segment": None, "wind_speed_unit": None,
                        "average_value": 0.16, "representative_value": None,
                    },
                    {
                        "tower_code": "0047#", "height": 90,
                        "wind_speed_segment": 15, "wind_speed_unit": "m/s",
                        "average_value": 0.124, "representative_value": 0.166,
                    },
                ],
            }
        }


def test_http_parser_defers_mapping_until_secondary(monkeypatch):
    """HTTP 入口与命令行入口使用相同的二次抽取后映射顺序。"""
    calls = []

    class RecordingPipeline:
        def parse(self, file_path, *, defer_mapping=False):
            calls.append(("primary", file_path, defer_mapping))
            return {"outputFiles": {"result": "result.json"}}

    def fake_enhance(parse_result, **kwargs):
        calls.append(("secondary", parse_result))
        return {"mapped": {"${project_name}": "测试项目"}}

    monkeypatch.setattr("word_parser.application.workflow.enhance_parse_result", fake_enhance)
    result = http_api._parse_downloaded_file(ParserService(RecordingPipeline()), "report.pdf")

    assert calls == [
        ("primary", "report.pdf", True),
        ("secondary", {"outputFiles": {"result": "result.json"}}),
    ]
    assert result["mapped"]["${project_name}"] == "测试项目"


def _request_body() -> dict:
    return {
        "bizId": 2001,
        "reportType": "FEASIBILITY_STUDY",
        "fileUrl": "https://oss.example.com/report/test.pdf",
        "fileName": "测试报告.pdf",
        "callbackUrl": "172.16.14.71:10100/ai/ai-project/report/parse/callback",
    }


def test_submit_parse_task_returns_task_id(monkeypatch):
    captured = {}

    async def fake_process(request, task_id, parser):
        captured["request"] = request
        captured["task_id"] = task_id
        captured["parser"] = parser

    parser = FakeParserService()
    monkeypatch.setattr(http_api, "_process_parse_task", fake_process)
    app.dependency_overrides[get_parser_service] = lambda: parser
    try:
        with TestClient(app) as client:
            response = client.post("/parse", json=_request_body())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["taskId"].startswith("PARSE-")
    assert captured["request"].bizId == 2001
    assert captured["task_id"] == response.json()["taskId"]
    assert captured["parser"] is parser


def test_process_parse_task_callbacks_success_payload(monkeypatch):
    callbacks = []

    async def fake_download(file_url: str, target: Path):
        assert file_url == "https://oss.example.com/report/test.pdf"
        target.write_bytes(b"test document")

    async def fake_callback(callback_url: str, payload):
        callbacks.append((callback_url, payload))

    monkeypatch.setattr(http_api, "_download_report", fake_download)
    monkeypatch.setattr(http_api, "_send_callback", fake_callback)
    request = ParseTaskRequest.model_validate(_request_body())

    asyncio.run(http_api._process_parse_task(request, "PARSE-001", FakeParserService()))

    assert len(callbacks) == 1
    callback_url, payload = callbacks[0]
    assert callback_url == "http://172.16.14.71:10100/ai/ai-project/report/parse/callback"
    assert payload.reportId == 2001
    assert payload.parseTaskId == "PARSE-001"
    assert payload.parseStatus == "SUCCESS"
    assert payload.errorMsg is None
    assert json.loads(payload.rawData) == {
        "${project_name}": "测试项目",
        "${air_density}": None,
        "${eachTierHeightTurbulenceTableList}": [
            {
                "tower_code": "0047#", "height": 90,
                "wind_speed_segment": None, "wind_speed_unit": None,
                "average_value": 0.16, "representative_value": None,
            },
            {
                "tower_code": "0047#", "height": 90,
                "wind_speed_segment": 15, "wind_speed_unit": "m/s",
                "average_value": 0.124, "representative_value": 0.166,
            },
        ],
    }


def test_process_parse_task_callbacks_failure_payload(monkeypatch):
    callbacks = []

    async def failed_download(file_url: str, target: Path):
        raise RuntimeError("文件下载失败")

    async def fake_callback(callback_url: str, payload):
        callbacks.append(payload)

    monkeypatch.setattr(http_api, "_download_report", failed_download)
    monkeypatch.setattr(http_api, "_send_callback", fake_callback)
    request = ParseTaskRequest.model_validate(_request_body())

    asyncio.run(http_api._process_parse_task(request, "PARSE-002", FakeParserService()))

    payload = callbacks[0]
    assert payload.reportId == 2001
    assert payload.parseStatus == "FAILED"
    assert payload.rawData is None
    assert payload.errorMsg == "文件下载失败"


def test_send_callback_accepts_code_200(monkeypatch):
    requests = []
    logs = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "data": True, "msg": ""})

    transport = httpx.MockTransport(handle_request)
    async_client = httpx.AsyncClient
    monkeypatch.setattr(
        http_api.httpx,
        "AsyncClient",
        lambda **kwargs: async_client(transport=transport, **kwargs),
    )
    monkeypatch.setattr(http_api.logger, "info", logs.append)
    payload = http_api.ParseCallbackPayload(
        reportId=98,
        parseTaskId="PARSE-001",
        parseStatus="SUCCESS",
        rawData='{"representative_value":null}',
        errorMsg=None,
    )

    asyncio.run(http_api._send_callback("http://callback.example.com/result", payload))

    assert len(requests) == 1
    assert json.loads(requests[0].content) == payload.model_dump()
    assert any("解析回调请求入参" in message and r'\"representative_value\":null' in message for message in logs)


def test_submit_parse_task_rejects_unsupported_file_type():
    request = _request_body()
    request["fileName"] = "notes.txt"
    app.dependency_overrides[get_parser_service] = lambda: FakeParserService()
    try:
        with TestClient(app) as client:
            response = client.post("/parse", json=request)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 415
    assert ".docx" in response.json()["detail"]


def test_cors_origins_are_normalized_and_deduplicated():
    assert http_api._cors_origins(" http://localhost:5173/,http://localhost:5173,http://127.0.0.1:5173 ") == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
