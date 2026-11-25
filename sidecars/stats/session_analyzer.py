#!/usr/bin/env python3
"""Standalone per-session transcript analyzer for the Antigravity side panel.

Reads only the open conversation's transcript.jsonl (stdlib-only, zero DB/port).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from typing import Any

USER_REQUEST_RE = re.compile(r"<USER_REQUEST>(.*?)</USER_REQUEST>", re.DOTALL | re.IGNORECASE)
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

CTX_WARN = 150_000
CTX_CRIT = 200_000
USD_TO_VND = 25_500

# USD per 1M tokens (input = uncached, output, cached = cache read)
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gemini-flash": {"input": 0.75, "output": 3.75, "cached": 0.075},
    "gemini-3.8-flash": {"input": 0.75, "output": 3.75, "cached": 0.075},
    "gemini-pro": {"input": 2.00, "output": 12.00, "cached": 0.20},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40, "cached": 0.025},
    "gemini-4-argon": {"input": 2.00, "output": 12.00, "cached": 0.20},
    "gemini-4-carbon": {"input": 1.25, "output": 10.00, "cached": 0.125},
    "gemini-4-hydrogen": {"input": 0.75, "output": 3.75, "cached": 0.075},
    "gemini-4-neon": {"input": 0.75, "output": 3.75, "cached": 0.075},
    "deepseek": {"input": 0.27, "output": 1.10, "cached": 0.07},
    "claude-sonnet": {"input": 3.00, "output": 15.00, "cached": 0.30},
    "claude-opus": {"input": 5.00, "output": 25.00, "cached": 0.50},
    "claude-haiku": {"input": 0.80, "output": 4.00, "cached": 0.08},
    "claude-fable": {"input": 5.00, "output": 25.00, "cached": 0.50},
    "gpt-4o": {"input": 2.50, "output": 10.00, "cached": 1.25},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached": 0.075},
    "gpt-5": {"input": 2.50, "output": 10.00, "cached": 1.25},
    "o3-mini": {"input": 1.10, "output": 4.40, "cached": 0.55},
    "o1": {"input": 15.00, "output": 60.00, "cached": 7.50},
    "default": {"input": 1.00, "output": 5.00, "cached": 0.10},
}


def _collapse_ws(text: str) -> str:
    return " ".join(text.split())


def _truncate(text: str, max_len: int = 120) -> str:
    return text if len(text) <= max_len else text[: max_len - 3].rstrip() + "..."


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _parse_iso(ts: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _get_pricing(model_name: str) -> dict[str, float]:
    low = (model_name or "").lower().strip()
    if not low:
        return MODEL_PRICING["default"]
    if low in MODEL_PRICING:
        return MODEL_PRICING[low]
    # Match longest prefix/substring
    for key in sorted(MODEL_PRICING.keys(), key=len, reverse=True):
        if key != "default" and key in low:
            return MODEL_PRICING[key]
    if "opus" in low:
        return MODEL_PRICING["claude-opus"]
    if "sonnet" in low:
        return MODEL_PRICING["claude-sonnet"]
    if "haiku" in low:
        return MODEL_PRICING["claude-haiku"]
    if "flash" in low:
        return MODEL_PRICING["gemini-flash"]
    if "pro" in low and "gemini" in low:
        return MODEL_PRICING["gemini-pro"]
    return MODEL_PRICING["default"]


def _step_cost_breakdown(model: str, uncached_in: int, cached_in: int, out_tok: int) -> dict[str, float]:
    p = _get_pricing(model)
    c_in = (uncached_in / 1_000_000.0) * p["input"]
    c_cache = (cached_in / 1_000_000.0) * p["cached"]
    c_out = (out_tok / 1_000_000.0) * p["output"]
    c_total = c_in + c_cache + c_out
    c_saved = (cached_in / 1_000_000.0) * max(0.0, p["input"] - p["cached"])
    return {
        "input_cost": c_in,
        "cache_cost": c_cache,
        "output_cost": c_out,
        "total_cost": c_total,
        "cache_saved": c_saved,
    }


def _extract_user_request(content: Any) -> str:
    if content is None:
        return ""
    raw = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    m = USER_REQUEST_RE.search(raw)
    return _collapse_ws(m.group(1)) if m else _collapse_ws(raw)


def _extract_tool_details(tool_calls: Any) -> list[dict[str, str]]:
    if not isinstance(tool_calls, list):
        return []
    out: list[dict[str, str]] = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            name = tc.get("name") or tc.get("tool_name") or tc.get("function", {}).get("name")
            if not name:
                continue
            raw_args = tc.get("args") or tc.get("arguments") or tc.get("function", {}).get("arguments")
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except Exception:
                    raw_args = None
            summary = ""
            if isinstance(raw_args, dict):
                if raw_args.get("toolSummary"):
                    summary = str(raw_args["toolSummary"])
                elif raw_args.get("focus"):
                    summary = str(raw_args["focus"])
                elif raw_args.get("Role"):
                    summary = f"{raw_args.get('TypeName', '')}: {raw_args['Role']}".strip(": ")
                elif raw_args.get("Path"):
                    summary = pathlib.PureWindowsPath(str(raw_args["Path"]).replace("/", "\\")).name or str(raw_args["Path"])
                elif raw_args.get("ToolName"):
                    srv = raw_args.get("ServerName", "")
                    summary = f"{srv}.{raw_args['ToolName']}".strip(".")
                elif raw_args.get("query"):
                    summary = str(raw_args["query"])
                elif raw_args.get("CommandLine"):
                    summary = _collapse_ws(str(raw_args["CommandLine"]))
            out.append({"name": str(name), "summary": _truncate(_collapse_ws(summary), 80)})
        elif isinstance(tc, str) and tc:
            out.append({"name": tc, "summary": ""})
    return out


def _fmt_num(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(int(round(n)))


def _fmt_usd(v: float) -> str:
    if v >= 1:
        return f"${v:.2f}"
    if v >= 0.01:
        return f"${v:.3f}"
    return f"${v:.4f}"


def _analyze_optimum(
    token_steps: list[dict[str, Any]],
    peak_ctx: int,
    overall_cache_pct: float,
    user_turns: int,
) -> dict[str, Any]:
    n = len(token_steps)
    costs = [s["cost"] for s in token_steps] or [0.0]
    if n >= 2:
        c_curr = max(token_steps[-1]["input_tokens"], token_steps[-2]["input_tokens"])
    elif n == 1:
        c_curr = token_steps[0]["input_tokens"]
    else:
        c_curr = peak_ctx

    w = max(3, round(n / 4)) if n else 1
    total_cost = sum(costs)
    mean_cost = total_cost / n if n > 0 else 0.0
    recent_costs = costs[-w:]
    marginal = sum(recent_costs) / max(1, len(recent_costs))
    ctx_pct = (c_curr or peak_ctx or 0) / CTX_CRIT

    if n < 4 or (n < 6 and c_curr < 50_000):
        turn_txt = f" ({user_turns} lượt hỏi)" if user_turns > 0 else ""
        return {
            "state": "wait",
            "label": "Mới bắt đầu",
            "score": 100,
            "current_context": c_curr,
            "ctx_pct": round(ctx_pct * 100, 1),
            "marginal_cost": marginal,
            "mean_cost": mean_cost,
            "recent_cache_pct": round(overall_cache_pct, 1),
            "delta_uncached": 0,
            "reason": f"Mới {n} bước{turn_txt}, ngữ cảnh {_fmt_num(c_curr)} — cứ tiếp tục thoải mái.",
        }

    w_ser = min(n, max(3, round(n / 4)))
    start_idx = max(1 if n > 1 else 0, n - w_ser)
    recent = token_steps[start_idx:]
    sum_in = sum(s["input_tokens"] for s in recent)
    sum_cached = sum(s["cached_tokens"] for s in recent)
    sum_uncached = sum(s["uncached_input_tokens"] for s in recent)
    r_cache = _clamp(sum_cached / sum_in, 0.0, 1.0) if sum_in > 0 else _clamp(overall_cache_pct / 100.0, 0.0, 1.0)
    delta_u = sum_uncached / max(1, len(recent))
    recent_cache_pct = r_cache * 100.0

    u = _clamp((c_curr - 20_000) / (CTX_CRIT - 20_000), 0.0, 1.2)
    p_ctx = _clamp(u ** 1.7, 0.0, 1.0)
    p_miss = _clamp((0.92 - r_cache) / 0.52, 0.0, 1.0)
    p_creep = _clamp((delta_u - 4_000) / 36_000, 0.0, 1.0)
    s_ctx = 0.0 if c_curr <= 25_000 else _clamp(c_curr / 50_000, 0.2, 1.0)
    p_econ = s_ctx * (0.55 * p_miss + 0.45 * p_creep)
    d_eff = (user_turns + 0.25 * max(0, n - user_turns)) if user_turns > 0 else (0.35 * n)
    p_depth = _clamp((d_eff - 10.0) / 35.0, 0.0, 1.0)

    w_total = 0.45 * p_ctx + 0.35 * p_econ + 0.20 * p_depth
    p_total = max(w_total, p_ctx ** 1.15)
    score = max(0, round(100 * (1.0 - _clamp(p_total, 0.0, 1.0))))

    if score >= 55:
        state, label = "ok", "Tiếp tục"
    elif score >= 25:
        state, label = "near", "Sắp tới hạn"
    else:
        state, label = "new", "Nên tạo mới"

    why: list[str] = []
    if c_curr >= CTX_CRIT:
        why.append(f"Ngữ cảnh {_fmt_num(c_curr)} đã vượt ngưỡng {_fmt_num(CTX_CRIT)}")
    elif c_curr >= CTX_WARN:
        why.append(f"Ngữ cảnh {_fmt_num(c_curr)} ({round(ctx_pct * 100)}% ngưỡng {_fmt_num(CTX_CRIT)}), sắp chạm trần")
    else:
        why.append(f"Ngữ cảnh {_fmt_num(c_curr)} ({round(ctx_pct * 100)}% ngưỡng {_fmt_num(CTX_CRIT)})")

    if delta_u >= 25_000 or (c_curr > 40_000 and recent_cache_pct < 65):
        why.append(f"cache gần đây thấp ({recent_cache_pct:.0f}%, nạp mới ~{_fmt_num(delta_u)} tok/bước)")
    elif recent_cache_pct >= 90 and delta_u <= 6_000:
        why.append(f"cache rất tốt ({recent_cache_pct:.0f}%, chỉ +{_fmt_num(delta_u)} tok mới/bước)")
    else:
        why.append(f"cache gần đây {recent_cache_pct:.0f}% (+{_fmt_num(delta_u)} tok mới/bước)")

    why.append(f"biên {_fmt_usd(marginal)}/bước vs TB {_fmt_usd(mean_cost)}/bước")

    return {
        "state": state,
        "label": label,
        "score": score,
        "current_context": c_curr,
        "ctx_pct": round(ctx_pct * 100, 1),
        "marginal_cost": marginal,
        "mean_cost": mean_cost,
        "recent_cache_pct": round(recent_cache_pct, 1),
        "delta_uncached": round(delta_u),
        "reason": "; ".join(why) + ".",
    }


def analyze_transcript(transcript_path: pathlib.Path, session_id: str) -> dict[str, Any]:
    lines = transcript_path.read_text(encoding="utf-8", errors="replace").splitlines()

    title = ""
    last_prompt = ""
    user_turn_count = 0
    tool_call_count = 0
    error_count = 0
    first_ts = 0
    last_ts = 0
    last_model = ""
    prev_dt: dt.datetime | None = None
    prev_ctx = 0

    total_uncached_in = 0
    total_cached_in = 0
    total_out = 0
    peak_ctx = 0

    total_input_cost = 0.0
    total_cache_cost = 0.0
    total_output_cost = 0.0
    total_cost = 0.0
    total_saved = 0.0

    models_map: dict[str, dict[str, Any]] = {}
    tools_map: dict[str, int] = {}
    turns_map: dict[int, dict[str, Any]] = {}
    steps: list[dict[str, Any]] = []
    token_steps: list[dict[str, Any]] = []

    cum_cost = 0.0

    for line_no, raw_line in enumerate(lines):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            step = json.loads(raw_line)
        except Exception:
            continue

        step_idx = step.get("step_index")
        if not isinstance(step_idx, int):
            step_idx = line_no

        step_type = str(step.get("type") or "")
        status_str = str(step.get("status") or "DONE").upper()
        err_raw = step.get("error")
        err_text = err_raw if isinstance(err_raw, str) else (json.dumps(err_raw, ensure_ascii=False) if err_raw is not None else "")
        if status_str == "ERROR" or err_text:
            error_count += 1

        raw_model = str(step.get("model") or "").strip()
        if raw_model:
            last_model = raw_model
        model_used = raw_model or last_model or "unknown"

        step_dt = _parse_iso(str(step.get("created_at") or ""))
        ts_sec = int(step_dt.timestamp()) if step_dt is not None else 0
        if ts_sec > 0:
            if first_ts == 0 or ts_sec < first_ts:
                first_ts = ts_sec
            if ts_sec > last_ts:
                last_ts = ts_sec

        duration_ms = 0
        if step_dt is not None and prev_dt is not None:
            diff = int((step_dt - prev_dt).total_seconds() * 1000)
            if 0 < diff <= 600_000:
                duration_ms = diff
        if step_dt is not None:
            prev_dt = step_dt

        tool_details = _extract_tool_details(step.get("tool_calls"))
        tool_names = [td["name"] for td in tool_details]
        if tool_names:
            tool_call_count += len(tool_names)
            for tn in tool_names:
                tools_map[tn] = tools_map.get(tn, 0) + 1

        content = step.get("content")
        if step_type == "USER_INPUT":
            user_turn_count += 1
            prompt_text = _extract_user_request(content)
            if prompt_text:
                if not title:
                    title = _truncate(prompt_text, 120)
                last_prompt = prompt_text
            turns_map[user_turn_count] = {
                "turn_index": user_turn_count,
                "step_index": step_idx,
                "timestamp": ts_sec,
                "text": _truncate(prompt_text, 200),
                "step_count": 0,
                "input_tokens": 0,
                "cached_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "tool_calls": 0,
            }
            preview = _truncate(prompt_text, 160)
        else:
            raw_preview = content if isinstance(content, str) else (json.dumps(content, ensure_ascii=False) if content is not None else "")
            preview = _truncate(_collapse_ws(raw_preview), 160)

        uncached_in = int(step.get("input_tokens") or 0)
        cached_in = int(step.get("cache_read_tokens") or 0)
        out_tok = int(step.get("output_tokens") or 0)
        total_in = uncached_in + cached_in
        total_tok = total_in + out_tok

        delta_ctx = 0
        if total_tok > 0:
            delta_ctx = total_in - prev_ctx if prev_ctx > 0 else total_in
            prev_ctx = total_in
            if total_in > peak_ctx:
                peak_ctx = total_in

        cb = _step_cost_breakdown(model_used, uncached_in, cached_in, out_tok) if total_tok > 0 else {
            "input_cost": 0.0, "cache_cost": 0.0, "output_cost": 0.0, "total_cost": 0.0, "cache_saved": 0.0
        }
        cum_cost += cb["total_cost"]

        if total_tok > 0:
            total_uncached_in += uncached_in
            total_cached_in += cached_in
            total_out += out_tok
            total_input_cost += cb["input_cost"]
            total_cache_cost += cb["cache_cost"]
            total_output_cost += cb["output_cost"]
            total_cost += cb["total_cost"]
            total_saved += cb["cache_saved"]

            m = models_map.setdefault(model_used, {
                "model": model_used, "steps": 0, "input_tokens": 0,
                "cached_tokens": 0, "output_tokens": 0, "cost": 0.0,
            })
            m["steps"] += 1
            m["input_tokens"] += total_in
            m["cached_tokens"] += cached_in
            m["output_tokens"] += out_tok
            m["cost"] += cb["total_cost"]

            if user_turn_count in turns_map:
                t = turns_map[user_turn_count]
                t["step_count"] += 1
                t["input_tokens"] += total_in
                t["cached_tokens"] += cached_in
                t["output_tokens"] += out_tok
                t["cost"] += cb["total_cost"]
                t["tool_calls"] += len(tool_names)

        step_obj = {
            "step_index": step_idx,
            "turn_index": user_turn_count,
            "timestamp": ts_sec,
            "type": step_type,
            "status": status_str,
            "model": model_used,
            "input_tokens": total_in,
            "uncached_input_tokens": uncached_in,
            "cached_tokens": cached_in,
            "output_tokens": out_tok,
            "total_tokens": total_tok,
            "delta_context": delta_ctx,
            "cache_hit_rate": round((cached_in / total_in) * 100.0, 1) if total_in > 0 else 0.0,
            "duration_ms": duration_ms,
            "cost": cb["total_cost"],
            "input_cost": cb["input_cost"],
            "cache_cost": cb["cache_cost"],
            "output_cost": cb["output_cost"],
            "cache_saved": cb["cache_saved"],
            "cum_cost": cum_cost,
            "tool_details": tool_details,
            "preview": preview,
            "error": _truncate(err_text, 240) if err_text else "",
        }
        steps.append(step_obj)
        if total_tok > 0:
            token_steps.append(step_obj)

    total_in_all = total_uncached_in + total_cached_in
    total_all = total_in_all + total_out
    cache_hit_pct = round((total_cached_in / total_in_all) * 100.0, 1) if total_in_all > 0 else 0.0
    models_list = sorted(models_map.values(), key=lambda x: (-x["cost"], -x["steps"]))
    primary_model = models_list[0]["model"] if models_list else (last_model or "unknown")
    tools_list = [{"name": k, "count": v} for k, v in sorted(tools_map.items(), key=lambda kv: (-kv[1], kv[0]))]
    turns_list = [turns_map[k] for k in sorted(turns_map.keys())]

    optimum = _analyze_optimum(token_steps, peak_ctx, cache_hit_pct, user_turn_count)

    return {
        "session_id": session_id,
        "title": title or f"Session {session_id[:8]}",
        "last_prompt": _truncate(last_prompt, 160),
        "primary_model": primary_model,
        "first_timestamp": first_ts,
        "last_timestamp": last_ts,
        "duration_seconds": max(0, last_ts - first_ts) if first_ts and last_ts else 0,
        "user_turn_count": user_turn_count,
        "token_step_count": len(token_steps),
        "total_step_count": len(steps),
        "tool_call_count": tool_call_count,
        "error_count": error_count,
        "usd_to_vnd": USD_TO_VND,
        "totals": {
            "input_tokens": total_in_all,
            "uncached_input_tokens": total_uncached_in,
            "cached_tokens": total_cached_in,
            "output_tokens": total_out,
            "total_tokens": total_all,
            "cache_hit_pct": cache_hit_pct,
            "peak_context": peak_ctx,
            "current_context": optimum["current_context"],
            "ctx_crit": CTX_CRIT,
            "total_cost": total_cost,
            "input_cost": total_input_cost,
            "cache_cost": total_cache_cost,
            "output_cost": total_output_cost,
            "cache_saved": total_saved,
            "cost_per_turn": total_cost / user_turn_count if user_turn_count > 0 else total_cost,
        },
        "optimum": optimum,
        "models": models_list,
        "tools": tools_list,
        "turns": turns_list,
        "steps": token_steps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze a single Antigravity transcript session")
    parser.add_argument("--transcript", required=True, help="Path to transcript.jsonl")
    parser.add_argument("--session-id", required=True, help="Conversation UUID")
    args = parser.parse_args()

    tp = pathlib.Path(args.transcript)
    if not tp.exists():
        print(json.dumps({"error": "no-transcript"}))
        return 0
    result = analyze_transcript(tp, args.session_id)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
