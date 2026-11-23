"""应用层异步报告解析 HTTP 接口。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from threading import Lock
from uuid import uuid4

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware

from word_parser.logger import logger
from word_parser.application.api import create_parser, enhance_parse_result
from word_parser.application.service import ParserService
from word_parser.application.workflow import run_full_parse


ALLOWED_DOCUMENT_SUFFIXES = {".doc", ".docx", ".pdf"}
MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
CALLBACK_RETRY_DELAYS = (0, 1, 3)

def _cors_origins(value: str | None = None) -> list[str]:
    configured = os.getenv("WORD_PARSER_CORS_ORIGINS", "") if value is None else value
    return list(dict.fromkeys(origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()))


app = FastAPI(title="WordParser API", version="1.0.0")
cors_origins = _cors_origins()
if cors_origins:
    allow_all_origins = "*" in cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all_origins else cors_origins,
        allow_credentials=not allow_all_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
_parser_lock = Lock()


class ParseTaskRequest(BaseModel):
    bizId: int = Field(gt=0)
    reportType: str = Field(min_length=1)
    fileUrl: AnyHttpUrl
    fileName: str = Field(min_length=1)
    callbackUrl: AnyHttpUrl

    @field_validator("callbackUrl", mode="before")
    @classmethod
    def normalize_callback_url(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized and "://" not in normalized:
                return f"http://{normalized}"
        return value


class ParseTaskResponse(BaseModel):
    taskId: str


class ParseCallbackPayload(BaseModel):
    reportId: int
    parseTaskId: str
    parseStatus: str
    rawData: str | None
    errorMsg: str | None


@lru_cache(maxsize=1)
def get_parser_service() -> ParserService:
    return create_parser()


def _new_task_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"PARSE-{timestamp}-{uuid4().hex[:8].upper()}"


def _document_suffix(request: ParseTaskRequest) -> str:
    return Path(request.fileName).suffix.lower()


def _parse_downloaded_file(parser: ParserService, file_path: str) -> dict:
    with _parser_lock:
        if isinstance(parser, ParserService):
            return run_full_parse(parser, file_path)
        result = parser.parse(file_path)
        if (result.get("outputFiles") or {}).get("result"):
            return enhance_parse_result(result)
        return result


async def _download_report(file_url: str, target: Path) -> None:
    downloaded_bytes = 0
    timeout = httpx.Timeout(120.0, connect=30.0)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        async with client.stream("GET", file_url) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > MAX_DOWNLOAD_BYTES:
                raise ValueError("下载文件不能超过 200 MB")
            with target.open("wb") as output:
                async for chunk in response.aiter_bytes(DOWNLOAD_CHUNK_BYTES):
                    downloaded_bytes += len(chunk)
                    if downloaded_bytes > MAX_DOWNLOAD_BYTES:
                        raise ValueError("下载文件不能超过 200 MB")
                    output.write(chunk)


async def _send_callback(callback_url: str, payload: ParseCallbackPayload) -> None:
    request_body = payload.model_dump()
    logger.info(
        f"解析回调请求入参 | 任务编号={payload.parseTaskId} "
        f"| 请求体={json.dumps(request_body, ensure_ascii=False, separators=(',', ':'))}"
    )
    last_error: Exception | None = None
    for delay in CALLBACK_RETRY_DELAYS:
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(
                    f"解析回调开始 | 任务编号={payload.parseTaskId} | 报告编号={payload.reportId} "
                    f"| 状态={payload.parseStatus}"
                )
                response = await client.post(callback_url, json=request_body)
                response.raise_for_status()
                response_body = response.json()
                if isinstance(response_body, dict) and response_body.get("code") not in (None, 0, 200):
                    raise RuntimeError(f"回调响应失败：{response_body}")
                return
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"解析结果回调失败：{last_error}") from last_error


async def _process_parse_task(
    request: ParseTaskRequest,
    task_id: str,
    parser: ParserService,
) -> None:
    callback_payload: ParseCallbackPayload
    try:
        safe_name = Path(request.fileName).name
        with tempfile.TemporaryDirectory(prefix="word_parser_task_") as temp_dir:
            report_path = Path(temp_dir) / safe_name
            await _download_report(str(request.fileUrl), report_path)
            with report_path.open("rb") as report_file:
                report_sha256 = hashlib.file_digest(report_file, "sha256").hexdigest()
            logger.info(
                f"解析任务输入 | 任务编号={task_id} | 文件名={safe_name} "
                f"| 文件字节数={report_path.stat().st_size} | 摘要={report_sha256}"
            )
            parse_result = await run_in_threadpool(_parse_downloaded_file, parser, str(report_path))

        mapped = parse_result.get("mapped")
        if not isinstance(mapped, dict):
            raise RuntimeError("解析结果缺少 mapped 数据")
        callback_payload = ParseCallbackPayload(
            reportId=request.bizId,
            parseTaskId=task_id,
            parseStatus="SUCCESS",
            rawData=json.dumps(mapped, ensure_ascii=False, separators=(",", ":")),
            errorMsg=None,
        )
    except Exception as exc:
        logger.exception(f"解析任务失败 | 任务编号={task_id} | 业务编号={request.bizId} | 原因={exc}")
        callback_payload = ParseCallbackPayload(
            reportId=request.bizId,
            parseTaskId=task_id,
            parseStatus="FAILED",
            rawData=None,
            errorMsg=str(exc)[:1000] or "文档解析失败",
        )

    try:
        await _send_callback(str(request.callbackUrl), callback_payload)
    except Exception as exc:
        logger.exception(f"解析回调失败 | 任务编号={task_id} | 业务编号={request.bizId} | 原因={exc}")


@app.post("/parse", response_model=ParseTaskResponse)
async def submit_parse_task(
    request: ParseTaskRequest,
    background_tasks: BackgroundTasks,
    parser: ParserService = Depends(get_parser_service),
) -> ParseTaskResponse:
    suffix = _document_suffix(request)
    if suffix not in ALLOWED_DOCUMENT_SUFFIXES:
        allowed = ", ".join(sorted(ALLOWED_DOCUMENT_SUFFIXES))
        raise HTTPException(status_code=415, detail=f"仅支持以下文件类型：{allowed}")

    task_id = _new_task_id()
    background_tasks.add_task(_process_parse_task, request, task_id, parser)
    return ParseTaskResponse(taskId=task_id)
