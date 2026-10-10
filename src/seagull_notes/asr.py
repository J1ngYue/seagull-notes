"""语音转写：faster-whisper 薄封装。

模型缓存锁到 E 盘（见 config.apply_hf_env），首次运行会自动下载。
显存不够时把 config.ASR_MODEL 降到 medium / small。
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config

_model = None
_model_lock = asyncio.Lock()
_pyav_patched = False


@dataclass
class Transcript:
    text: str
    segments: list[dict[str, Any]]
    duration: float
    language: str
    origin: str          # "platform_subtitle" | "asr"
    pass_used: str = "vad"   # "vad" | "no_vad" | "hallucination_suspected"


def _patch_pyav_compat() -> None:
    """修 faster-whisper 1.2.1 与 PyAV 19 的不兼容。

    faster-whisper 调 av.open(..., metadata_errors="ignore")，
    但 PyAV 19 把这个参数挪进了 options 字典，直接传会 TypeError。
    给 av.open 包一层，把旧式关键字转成新式写法。
    """
    global _pyav_patched
    if _pyav_patched:
        return

    import av

    _original_open = av.open

    def compat_open(*args, **kwargs):
        metadata_errors = kwargs.pop("metadata_errors", None)
        if metadata_errors is not None:
            opts = dict(kwargs.get("options") or {})
            opts.setdefault("metadata_errors", metadata_errors)
            kwargs["options"] = opts
        return _original_open(*args, **kwargs)

    av.open = compat_open

    # faster_whisper.audio 里如果是 from av import open，就得单独补一刀
    try:
        from faster_whisper import audio as fw_audio

        module_av = getattr(fw_audio, "av", None)
        if module_av is not None and getattr(module_av, "open", None) is _original_open:
            module_av.open = compat_open
    except Exception:                                           # noqa: BLE001
        pass

    _pyav_patched = True


def _register_cuda_dlls() -> list[str]:
    """把 pip 装的 CUDA 12 运行时加进 DLL 搜索路径。

    ctranslate2 4.x 要 cublas64_12.dll 和 cudnn64_9.dll。系统里装的是 CUDA 11.8
    的话这两个找不到，加载模型时报 "Library cublas64_12.dll is not found"。

    光用 os.add_dll_directory 不够——ctranslate2 的 native 模块是 pybind11 写的，
    走的是 LoadLibrary，只认 PATH。所以两边都塞。
    """
    import os
    import sysconfig

    if sys.platform != "win32":
        return []

    site_packages = Path(sysconfig.get_paths()["purelib"])
    candidates = [
        site_packages / "nvidia" / "cublas" / "bin",
        site_packages / "nvidia" / "cudnn" / "bin",
        site_packages / "nvidia" / "cuda_nvrtc" / "bin",
        site_packages / "nvidia" / "cuda_runtime" / "bin",
        site_packages / "ctranslate2",
    ]

    registered: list[str] = []
    path_entries = os.environ.get("PATH", "").split(os.pathsep)

    for path in candidates:
        if not path.is_dir():
            continue
        resolved = str(path)
        try:
            os.add_dll_directory(resolved)
        except OSError:
            pass
        if resolved not in path_entries:
            path_entries.insert(0, resolved)
        registered.append(resolved)

    os.environ["PATH"] = os.pathsep.join(path_entries)
    return registered


def _load_model():
    """单例。模型加载慢，进程内只做一次。"""
    global _model
    if _model is None:
        _patch_pyav_compat()
        _register_cuda_dlls()
        from faster_whisper import WhisperModel

        config.apply_hf_env()
        cached_path = _cached_model_path()
        _model = WhisperModel(
            str(cached_path) if cached_path else config.ASR_MODEL,
            device=config.ASR_DEVICE,
            compute_type=config.ASR_COMPUTE_TYPE,
            download_root=str(config.HF_HUB_CACHE),
        )
    return _model


def _looks_like_hallucination(segments: list[dict[str, Any]]) -> bool:
    """判断是不是 Whisper 的复读幻觉。

    音频太安静、全是背景音乐、或者噪声大时，Whisper 会输出高度重复的
    样板文本（中文里常见"作词曲 XX 演唱 XX"、"字幕由 XX 提供"之类）。
    特征：段落少但每段几乎一样。
    """
    if len(segments) < 3:
        return False

    texts = [s["text"].strip() for s in segments if s.get("text", "").strip()]
    if len(texts) < 3:
        return False

    # 完全重复
    if len(set(texts)) <= max(1, len(texts) // 4):
        return True

    # 开头几个字高度雷同
    prefixes = [t[:6] for t in texts if len(t) >= 6]
    if len(prefixes) >= 3 and len(set(prefixes)) <= max(1, len(prefixes) // 3):
        return True

    return False


def _run_pass(model, media_path: Path, language: str | None, *,
              use_vad: bool, condition_on_previous: bool = True):
    """跑一次识别，返回 (segments, info)。

    condition_on_previous=False 能有效打断 Whisper 的复读循环——
    纯音乐或噪声大的音频很容易让它陷进"XX 演唱 XX"这种样板输出。
    """
    kwargs: dict[str, Any] = {
        "language": language,
        "beam_size": 5,
        "vad_filter": use_vad,
        "condition_on_previous_text": condition_on_previous,
        # 温度阶梯：正常温度出问题时自动升温重试，也是抗复读的标准手段
        "temperature": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
    }
    if use_vad:
        kwargs["vad_parameters"] = {"min_silence_duration_ms": 500}

    segments_iter, info = model.transcribe(str(media_path), **kwargs)

    segments: list[dict[str, Any]] = []
    for seg in segments_iter:                  # 生成器，迭代时才真正跑推理
        text = seg.text.strip()
        if not text:
            continue
        segments.append({"start": round(seg.start, 2), "end": round(seg.end, 2), "text": text})
    return segments, info


def _transcribe_sync(media_path: Path, language: str | None) -> Transcript:
    """识别音频，分三级降级。

    1. VAD + 上下文关联（正常情况，最快最准）
    2. VAD 滤空了 → 关 VAD 重跑
    3. 输出是复读幻觉 → 关上下文关联重跑（打断复读循环）
    """
    model = _load_model()

    segments, info = _run_pass(model, media_path, language, use_vad=True)
    path_used = "vad"

    if not segments:
        segments, info = _run_pass(model, media_path, language, use_vad=False)
        path_used = "no_vad"

    if segments and _looks_like_hallucination(segments):
        retry, retry_info = _run_pass(
            model, media_path, language, use_vad=False, condition_on_previous=False,
        )
        # 只有明显更好才采纳——短不代表好
        if retry and not _looks_like_hallucination(retry):
            segments, info = retry, retry_info
            path_used = "retry_no_context"
        else:
            path_used = "hallucination_suspected"

    parts = [s["text"] for s in segments]
    return Transcript(
        text="\n".join(parts),
        segments=segments,
        duration=float(getattr(info, "duration", 0.0) or 0.0),
        language=getattr(info, "language", language or "unknown"),
        origin="asr",
        pass_used=path_used,
    )


async def transcribe(media_path: Path, language: str | None = "zh") -> Transcript:
    """异步转写。推理吃满 GPU，用锁保证同一时刻只跑一个。"""
    async with _model_lock:
        return await asyncio.to_thread(_transcribe_sync, media_path, language)


def _cached_model_path() -> Path | None:
    """只认可完整快照，避免把下载留下的空目录当成可用模型。"""
    snapshots = config.HF_HUB_CACHE / f"models--Systran--faster-whisper-{config.ASR_MODEL}" / "snapshots"
    if not snapshots.is_dir():
        return None
    required = ("model.bin", "config.json", "tokenizer.json", "vocabulary.json")
    for snapshot in sorted(snapshots.iterdir()):
        if all((snapshot / name).is_file() and (snapshot / name).stat().st_size > 0 for name in required):
            return snapshot
    return None


def model_is_cached() -> bool:
    return _cached_model_path() is not None


def _prefetch_sync() -> Path:
    """下载模型到本地缓存，不做推理。"""
    config.apply_hf_env()
    config.ensure_dirs()
    from huggingface_hub import snapshot_download

    repo_id = f"Systran/faster-whisper-{config.ASR_MODEL}"
    path = snapshot_download(repo_id=repo_id, cache_dir=str(config.HF_HUB_CACHE))
    return Path(path)


async def prefetch_model() -> Path:
    """异步预下载模型。首次跑大模型时建议先执行这个。"""
    return await asyncio.to_thread(_prefetch_sync)
