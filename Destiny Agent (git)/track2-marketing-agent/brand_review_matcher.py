"""공개된 운명원 후기와 분석된 영상 주제의 관련성을 검색한다.

이 모듈은 게시물을 작성하거나 후기를 작성자 본인의 경험으로 바꾸지 않는다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

BASE = Path(__file__).resolve().parent


def load_brand_reviews(path: str | Path | None = None) -> list[dict[str, Any]]:
    src = Path(path) if path is not None else BASE / "brand_reviews.json"
    data = json.loads(src.read_text(encoding="utf-8"))
    reviews = data.get("reviews", [])
    if not isinstance(reviews, list):
        raise ValueError("reviews 항목은 배열이어야 합니다.")
    return reviews


def _analysis_text(analysis: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("topic", "core_problem", "title"):
        value = analysis.get(key)
        if isinstance(value, str):
            parts.append(value)
    for key in ("claims", "discussion_angles", "audience_reactions"):
        for entry in (analysis.get(key) or [])[:8]:
            if isinstance(entry, str):
                parts.append(entry)
            elif isinstance(entry, dict):
                for subkey in ("claim", "summary", "theme", "angle", "evidence"):
                    value = entry.get(subkey)
                    if isinstance(value, str):
                        parts.append(value)
    return " ".join(parts).lower()


def match_brand_reviews(
    analysis: dict[str, Any], max_results: int = 2
) -> list[dict[str, Any]]:
    """주제 키워드 교집합 기준의 보수적 검색. 일치하지 않으면 빈 배열.

    검색 점수는 추천 여부 또는 후기 사실 여부의 검증 점수가 아니다.
    """
    if not isinstance(analysis, dict):
        return []
    text = _analysis_text(analysis)
    results: list[dict[str, Any]] = []
    for review in load_brand_reviews():
        matched = [tag for tag in review.get("tags", []) if tag.lower() in text]
        if not matched:
            continue
        item = dict(review)
        item["matched_tags"] = matched
        item["match_score"] = len(matched)
        results.append(item)
    results.sort(key=lambda x: (-x["match_score"], x["id"]))
    return results[:max(0, max_results)]


if __name__ == "__main__":
    demo = {"topic": "파혼 후 새로운 인연을 만나는 것이 두렵다", "core_problem": "이별 뒤 결혼 불안"}
    for row in match_brand_reviews(demo):
        print(row["id"], row["topic"], row["matched_tags"])
