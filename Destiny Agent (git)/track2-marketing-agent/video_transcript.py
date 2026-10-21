"""YouTube 공개 자막을 가져오는 독립 모듈.

사용: python video_transcript.py https://youtu.be/VIDEO_ID
우선순위: 한국어 수동 → 한국어 자동 → 영어 수동 → 영어 자동.
자막을 가져오지 못하면 추측한 대본 대신 명시적 오류를 반환한다.
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

import yt_dlp


@dataclass
class TranscriptResult:
    video_id: str
    language: str
    source: str  # manual / automatic
    text: str
    segments: list[dict]


class TranscriptUnavailable(RuntimeError):
    """영상에서 사용 가능한 자막을 찾거나 읽지 못했음."""


def _video_id(url: str) -> str:
    from urllib.parse import urlparse, parse_qs
    p = urlparse(url)
    host = (p.hostname or '').lower()
    if host in ('youtu.be', 'www.youtu.be'):
        val = p.path.strip('/').split('/')[0]
    elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        val = parse_qs(p.query).get('v', [''])[0]
        if not val and p.path.startswith('/shorts/'):
            val = p.path.split('/')[2]
    else:
        val = ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', val):
        raise ValueError('유효한 YouTube 영상 URL이 아닙니다.')
    return val


def _preferred_tracks(info: dict) -> list[tuple[str, str, dict]]:
    tracks = []
    for source, field in (('manual', 'subtitles'), ('automatic', 'automatic_captions')):
        for lang, variants in (info.get(field) or {}).items():
            if not (lang == 'ko' or lang.startswith('ko-') or lang == 'en' or lang.startswith('en-')):
                continue
            for tr in variants:
                if tr.get('url') and tr.get('ext') in ('vtt', 'json3', 'srv3', 'ttml'):
                    tracks.append((lang, source, tr))
    def rank(t):
        lang, source, tr = t
        return (0 if lang.startswith('ko') else 1, 0 if source == 'manual' else 1,
                {'vtt':0, 'json3':1, 'srv3':2, 'ttml':3}.get(tr.get('ext'), 9))
    return sorted(tracks, key=rank)


def _stamp(s: str) -> float:
    pieces = s.replace(',', '.').split(':')
    try:
        seconds = float(pieces[-1]) + 60 * float(pieces[-2])
        if len(pieces) == 3:
            seconds += 3600 * float(pieces[0])
        return seconds
    except (ValueError, IndexError):
        return 0.0


def _clean(text: str) -> str:
    text = re.sub(r'<[^>]+>', '', text)
    return re.sub(r'\s+', ' ', html.unescape(text)).strip()


def _parse_vtt(data: str) -> list[dict]:
    segments = []
    for block in re.split(r'\n\s*\n', data.replace('\r\n', '\n')):
        lines = block.splitlines()
        mark = next((i for i, ln in enumerate(lines) if '-->' in ln), None)
        if mark is None:
            continue
        start = _stamp(lines[mark].split('-->')[0].strip())
        pieces = [_clean(line) for line in lines[mark+1:] if line.strip()]
        content = ' '.join(p for p in pieces if p)
        if content and (not segments or segments[-1]['text'] != content):
            segments.append({'start': start, 'text': content})
    return segments


def _parse_json3(data: str) -> list[dict]:
    obj = json.loads(data)
    segments = []
    for event in obj.get('events', []):
        content = _clean(''.join(seg.get('utf8', '') for seg in event.get('segs', [])))
        if content and (not segments or segments[-1]['text'] != content):
            segments.append({'start': event.get('tStartMs', 0)/1000, 'text': content})
    return segments


def _parse_xml(data: str) -> list[dict]:
    root = ET.fromstring(data)
    segments = []
    for elem in root.iter():
        if elem.tag.split('}')[-1] not in ('text', 'p'):
            continue
        content = _clean(''.join(elem.itertext()))
        if content:
            raw = elem.attrib.get('start', elem.attrib.get('t', '0'))
            start = float(raw)/1000 if 't' in elem.attrib else float(raw)
            segments.append({'start': start, 'text': content})
    return segments


def get_transcript(video_url: str, max_chars: int = 12000) -> TranscriptResult:
    vid = _video_id(video_url)
    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'skip_download': True,
                           'extract_flat': False, 'extractor_args': {'youtube': {'lang': ['ko']}}}) as ydl:
        try:
            info = ydl.extract_info('https://www.youtube.com/watch?v=' + vid, download=False)
        except Exception as exc:
            raise TranscriptUnavailable(f'영상 정보 조회 실패: {exc}') from exc

    tracks = _preferred_tracks(info or {})
    if not tracks:
        raise TranscriptUnavailable('이 영상에 접근 가능한 한국어 또는 영어 자막이 없습니다.')
    errors = []
    for language, source, tr in tracks:
        try:
            request = urllib.request.Request(tr['url'], headers={
                'User-Agent': 'Mozilla/5.0', 'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.8'})
            with urllib.request.urlopen(request, timeout=18) as response:
                raw = response.read(3_000_000).decode('utf-8-sig', errors='replace')
            ext = tr['ext']
            if ext == 'vtt':
                segments = _parse_vtt(raw)
            elif ext == 'json3':
                segments = _parse_json3(raw)
            else:
                segments = _parse_xml(raw)
            if not segments:
                errors.append(f'{language}/{source}: 자막 내용 없음')
                continue
            selected = []
            size = 0
            for seg in segments:
                if size + len(seg['text']) > max_chars:
                    break
                selected.append(seg)
                size += len(seg['text'])
            if not selected:
                raise TranscriptUnavailable('가져온 자막이 비어 있습니다.')
            return TranscriptResult(vid, language, source,
                                    '\n'.join(f"[{int(s['start']//60):02d}:{int(s['start']%60):02d}] {s['text']}" for s in selected),
                                    selected)
        except Exception as exc:
            errors.append(f'{language}/{source}: {str(exc)[:110]}')
    raise TranscriptUnavailable('자막을 읽지 못했습니다. ' + '; '.join(errors[:3]))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('사용: python video_transcript.py https://youtu.be/영상ID')
        sys.exit(2)
    try:
        result = get_transcript(sys.argv[1])
        print(f'자막 확보: {result.language}, {result.source}, {len(result.segments)}개 구간')
        print(result.text[:2800])
    except (TranscriptUnavailable, ValueError) as error:
        print('자막 수집 실패:', error)
        sys.exit(1)
