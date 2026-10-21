from pathlib import Path
import streamlit as st
import yaml
from ai_agent import generate_ai_comment
from youtube_oauth import get_my_channel
from validation import get_video_id, verify_video
from history import stats, reserve, finish, last_rows
from video_cards import enrich_videos, render_video_cards
from video_analysis import analyze_video, save_report
from chrome_comment import post_comment_visible

BASE = Path(__file__).resolve().parent
st.set_page_config(page_title="운명원 마케팅 AI 에이전트", page_icon="🎬", layout="wide")

st.markdown("""
<style>
/* 드롭다운 목록 전체 높이 및 스크롤 */
ul[role="listbox"] {
    max-height: 450px !important;
    overflow-y: auto !important;
}

/* 드롭다운 항목의 긴 제목 줄바꿈 */
ul[role="listbox"] li,
ul[role="listbox"] li * {
    white-space: normal !important;
    overflow-wrap: anywhere !important;
    word-break: keep-all !important;
    height: auto !important;
    min-height: 44px !important;
    line-height: 1.5 !important;
}

/* 선택된 영상 제목의 줄바꿈 */
div[data-baseweb="select"] [role="combobox"] {
    height: auto !important;
    min-height: 48px !important;
}

div[data-baseweb="select"] [role="combobox"] * {
    white-space: normal !important;
    overflow-wrap: anywhere !important;
    word-break: keep-all !important;
}
</style>
""", unsafe_allow_html=True)

with open(BASE / "config.yaml", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
CHANNELS = cfg['channels']
ALLOWED = {c['id'] for c in CHANNELS}
DAILY_MAX = int(cfg.get('limits', {}).get('daily_max_comments', 10))
PROFILE_NAMES = ['유튜브1','유튜브2','유튜브3']
for key, initial in {'videos': [], 'display_videos': [], 'draft': '', 'summary': '', 'last_video': '', 'events': [], 'last_post_result': None}.items():
    if key not in st.session_state:
        st.session_state[key] = initial

def sync_draft():
    st.session_state.draft = st.session_state.draft_box


@st.cache_data(ttl=300, show_spinner=False)
def load_channel_videos(channel_id, maximum=5):
    import subprocess
    import sys
    import re

    url = f"https://www.youtube.com/channel/{channel_id}/videos"

    cmd = [
        sys.executable, "-X", "utf8",
        "-m", "yt_dlp",
        "--flat-playlist",
        "--playlist-end", str(maximum),
        "--extractor-args", "youtube:lang=ko",
        "--no-warnings",
        "--print", "%(id)s\t%(title)s",
        url
    ]


    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90
    )


    videos = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue

        video_id, title = parts
        if not re.fullmatch(r"[\w-]{11}", video_id):
            continue

        videos.append({
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "title": title.strip(),
            "channel_id": channel_id
        })

    if result.returncode != 0:
        error = re.sub(r"\x1b\[[0-9;]*m", "", result.stderr)
        if not videos:
            raise RuntimeError(error[-600:] or "영상 목록 조회 실패")

    return videos


with st.sidebar:
    st.title('설정 & 브랜딩')
    st.write('운명원 | 연애 사주')
    st.caption('댓글은 영상의 구체적인 내용에 반응하고, 운명원과의 관계를 명시합니다. 허위 경험담과 광고 위장 표현은 사용하지 않습니다.')
    comment_range = st.slider('댓글 글자 수 범위', 40, 120, (40,120))
    st.write(f'하루 게시 상한: {DAILY_MAX}건')
    st.info('실제 게시 모드 · 전용 Chrome 프로필 사용')

st.title('운명원 유튜브 마케팅 AI 에이전트')
st.caption('영상 불러오기 → 초안 작성 및 승인 → 실제 크롬에서 게시·확인')
col1,col2,col3=st.columns(3, gap='medium')

with col1:
    with st.container(border=True):
        st.subheader('1. 영상 불러오기')
        keyword=st.text_input('제목 필터 (선택)', placeholder='예: 연애, 사주')
        if st.button('지정 채널 최신 영상 불러오기', use_container_width=True):
            videos=[]; errors=[]
            with st.spinner('지정 채널 최신 영상 수집 중...'):
                for ch in CHANNELS:
                    try:
                        for v in load_channel_videos(ch['id'],5):
                            if not keyword or keyword.lower() in v['title'].lower():
                                v['channel']=ch['name']; videos.append(v)
                    except Exception as exc:
                        errors.append(f"{ch['name']}: {exc}")
            st.session_state.videos=list({get_video_id(v['url']):v for v in videos}.values())
            st.session_state.display_videos=enrich_videos(st.session_state.videos)
            if errors: st.warning('일부 채널 조회 오류: ' + '; '.join(errors))
            st.success(f'{len(st.session_state.videos)}개 영상 불러옴')
        url=st.text_input('영상 링크 직접 입력',placeholder='https://youtu.be/...')
        if st.button('검증 후 링크 추가',use_container_width=True):
            try:
                info=verify_video(url,ALLOWED)
                item={'url':f"https://www.youtube.com/watch?v={info['video_id']}",'title':info['title'],'channel':info['channel'],'channel_id':info['channel_id']}
                st.session_state.videos=[item]+[v for v in st.session_state.videos if get_video_id(v['url']) != info['video_id']]
                st.session_state.display_videos=enrich_videos(st.session_state.videos)
                st.success('실제 채널 ID 검증 완료')
            except Exception as exc:
                st.error(str(exc))

        st.divider()

        if st.session_state.videos:
            render_video_cards(st.session_state.display_videos or st.session_state.videos)

        else:
            st.info("불러온 영상이 없습니다.")


with col2:
    with st.container(border=True):
        st.subheader('2. 영상 선택 & AI 초안')

        videos = st.session_state.videos

        if videos:
            indices = list(range(len(videos)))

            idx = st.selectbox(
                '영상 선택',
                indices,
                format_func=lambda i: (
                    f"[{videos[i].get('channel', '')}] "
                    f"{videos[i]['title']}"
                )
            )

            selected = videos[idx]
            vid = get_video_id(selected['url'])

            # 선택한 영상의 전체 제목 표시
            st.caption("현재 선택한 영상")
            st.info(selected['title'])

            # 다른 영상으로 변경하면 기존 초안 초기화
            if st.session_state.last_video != vid:
                st.session_state.last_video = vid
                st.session_state.draft = ''
                st.session_state.draft_box = ''
                st.session_state.summary = ''

            # 영상 분석 및 AI 댓글 생성
            if st.button(
                '영상 정보 확인 & 초안 생성',
                use_container_width=True
            ):
                try:
                    with st.spinner(
                        '영상 자막 및 인기 댓글 분석 중...'
                    ):
                        # 1. 영상 및 채널 검증
                        info = verify_video(
                            selected['url'],
                            ALLOWED
                        )

                        title = info['title']

                        # 2. 실제 자막과 인기 댓글 분석
                        analysis = analyze_video(
                            selected['url'],
                            account="유튜브1"
                        )

                        print("\n========== 영상 분석 진단 ==========", flush=True)
                        print("claims:", repr(analysis.get("claims")), flush=True)
                        print("topic:", repr(analysis.get("topic")), flush=True)
                        print("core_problem:", repr(analysis.get("core_problem")), flush=True)
                        print("==================================\n", flush=True)

                        # 3. 영상 속 핵심 연애 고민 한 줄 표시
                        st.session_state.summary = (
                            analysis.get("core_problem")
                            or analysis.get("topic")
                            or "영상의 핵심 고민을 확인하지 못했습니다."
                        )

                        # 4. 영상 분석 결과 저장
                        save_report(analysis)

                        # 5. 실제 분석 결과로 AI 댓글 생성
                        draft = generate_ai_comment(
                            video_title=title,
                            user_keyword=keyword,
                            min_len=comment_range[0],
                            max_len=comment_range[1],
                            analysis=analysis
                        )

                        # 6. 초안 생성 오류 확인
                        if not draft or draft.startswith('['):
                            raise ValueError(
                                draft or "AI 초안이 비어 있습니다."
                            )

                        # 7. 생성된 댓글 저장
                        st.session_state.draft = draft
                        st.session_state.draft_box = draft

                    st.success(
                        '영상 분석 및 댓글 초안 생성 완료'
                    )

                except Exception as exc:
                    st.error(
                        f'초안 생성 오류: {exc}'
                    )

            # 영상 속 연애 고민 한 줄
            st.text_area(
                '영상 속 핵심 연애 고민',
                value=st.session_state.summary,
                height=100,
                disabled=True
            )

            # 생성된 댓글 편집
            st.text_area(
                '댓글 편집',
                key='draft_box',
                height=180,
                on_change=sync_draft
            )

            # 댓글 글자 수 표시
            current_len = len(
                st.session_state.draft_box
            )

            st.caption(
                f"{current_len}자 / "
                f"{comment_range[0]}~{comment_range[1]}자"
            )

        else:
            selected = None
            st.info('먼저 영상을 불러오세요.')


with col3:
    with st.container(border=True):
        st.subheader('3. 댓글 달기 & 상태')
        account=st.selectbox('게시할 유튜브 계정',PROFILE_NAMES)

        if st.button("YouTube API 계정 확인"):
            try:
                channel = get_my_channel(account)
                st.success(
                    f"API 연결 채널: {channel['title']} (Chrome 로그인과 별개)"
                )
            except Exception as exc:
                st.error(f"인증 확인 실패: {exc}")

        profile_dir=BASE / 'profiles' / account
        st.caption(f'프로필 폴더: {profile_dir}')
        st.info('게시 전에 선택한 Chrome 프로필의 Google 로그인 상태를 확인하세요.')
        confirmed=st.checkbox('댓글을 제대로 확인했습니다. 실제 유튜브 영상 댓글에 게시하는 것에 동의합니다.')
        vid = get_video_id(selected['url']) if selected else ''

        status, today, full = (
            stats(vid, account, DAILY_MAX)
            if vid else (None, 0, False)
        )

        if status: st.warning(f'영상 게시 기록이 존재합니다: {status} · 중복 차단')
        st.write(f'오늘 게시시도: {today}/{DAILY_MAX}')
        if st.button('크롬으로 실제 댓글 게시',use_container_width=True,disabled=not (selected and confirmed and not status and not full)):
            comment=st.session_state.draft_box.strip()
            if not (comment_range[0] <= len(comment) <= comment_range[1]):
                st.error('댓글 글자 수 범위가 맞지 않습니다.')
            elif any(x in comment.lower() for x in ['http://','https://','www.','#']):
                st.error('댓글에 링크나 해시태그를 넣을 수 없습니다.')
            else:
                try:
                    with st.spinner('실제 채널 소유권 재확인 중...'):
                        info=verify_video(selected['url'],ALLOWED)
                    reserved,msg=reserve(vid,info['channel_id'],account,comment,DAILY_MAX)
                    if not reserved:
                        st.error(msg)
                    else:
                        with st.status('Chrome 게시 준비 중', expanded=True) as ui:
                            stages = [
                                'Chrome 프로필 여는 중',
                                '영상 및 댓글 입력창 찾는 중',
                                '댓글 한 글자씩 입력 중',
                                'YouTube 게시 버튼 클릭',
                                '게시한 댓글 화면 확인 중',
                            ]
                            progress = st.progress(0, text='게시 작업 시작')
                            stage_text = st.empty()
                            stage_text.caption('대기 중: Chrome 프로필 확인')
                            log_box = st.container()
                            messages = []

                            def update(message):
                                message = str(message)
                                messages.append(message)
                                with log_box:
                                    st.caption(message)
                                if '프로필 여는 중' in message:
                                    progress.progress(10, text='1/5 Chrome 프로필 여는 중')
                                elif '입력창' in message or '댓글 영역' in message:
                                    progress.progress(30, text='2/5 댓글 입력창 찾는 중')
                                elif '타이핑' in message or '입력 중' in message:
                                    progress.progress(55, text='3/5 한 글자씩 입력 중')
                                elif '게시 버튼' in message:
                                    progress.progress(75, text='4/5 게시 버튼 클릭')
                                elif '화면에 나타나는지' in message or '댓글 확인 중' in message:
                                    progress.progress(90, text='5/5 게시 댓글 확인 중')
                                elif '화면에서 확인했습니다' in message:
                                    progress.progress(100, text='게시 완료 · 댓글 확인됨')
                                stage_text.caption('현재: ' + message)

                            try:
                                result = post_comment_visible(
                                    video_url=selected['url'],
                                    comment=comment,
                                    account=account,
                                    base_dir=BASE,
                                    update=update,
                                )
                                success = bool(result.get('success'))
                                msg = result.get('message', '게시 결과를 확인하지 못했습니다.')
                                screenshot = result.get('screenshot')
                            except Exception as exc:
                                success = False
                                msg = f'{type(exc).__name__}: {exc}'
                                screenshot = None
                                update(msg)

                            # DB 결과 저장: 확인 불가능한 게시 결과는 중복 방지를 위해 잠금 유지
                            finish(vid, account, success, msg, screenshot)
                            st.session_state.last_post_result = {
                                'video_id': vid, 'account': account,
                                'success': success, 'message': msg,
                                'screenshot': screenshot, 'events': messages[:],
                            }
                            if success:
                                progress.progress(100, text='게시 완료 · 댓글 보기')
                                ui.update(label='Chrome 댓글 게시·화면 확인 완료', state='complete', expanded=False)
                                st.success('댓글이 게시되었고 YouTube 화면에서 확인했습니다.')
                                st.link_button('YouTube에서 댓글 보기', selected['url'], use_container_width=True)
                            else:
                                ui.update(label='실패 또는 확인 불가 · 기록 잠금', state='error', expanded=True)
                                st.error(msg)
                                st.caption('중복 게시를 막기 위해 해당 영상·계정은 수동 확인 전까지 잠금 상태로 유지됩니다.')
                                if screenshot:
                                    shot_path = Path(screenshot)
                                    if shot_path.is_file():
                                        st.image(str(shot_path), caption='오류 발생 당시 Chrome 화면', use_container_width=True)
                                        with shot_path.open('rb') as f:
                                            st.download_button('오류 화면 PNG 저장', data=f.read(), file_name=shot_path.name, mime='image/png')
                                    else:
                                        st.code(screenshot)

                except Exception as exc:
                    st.error(f'검증 또는 저장 오류: {exc}')

        
        st.divider()
        st.subheader("댓글 게시 이력")
        st.caption("최신순 · 영상별 게시 계정 및 실제 댓글 기록")
        
        status_labels = {
            "confirmed": "게시 확인",
            "pending": "게시 진행 중",
            "uncertain": "확인 필요",
            "failed": "게시 실패",
        }

        rows = last_rows(20)

        if not rows:
            st.info("아직 게시 기록이 없습니다.")

        for at, v, a, s, message, shot, posted_comment in rows:

            # 현재 불러온 영상 목록에서 제목 검색
            video_title = next(
                (
                    item.get("title", v)
                    for item in st.session_state.videos
                    if get_video_id(item["url"]) == v
                ),
                v
            )
        
            label = status_labels.get(s, s)
        
            with st.expander(
                f"{label} | {video_title}",
                expanded=False
            ):
                # 게시 상태
                if s == "confirmed":
                    st.success("게시 확인 완료")
                elif s == "pending":
                    st.info("게시 진행 중")
                elif s == "uncertain":
                    st.warning("실제 게시 여부를 확인해야 합니다.")
                else:
                    st.error("게시 실패")
        
                # 게시 정보
                st.write(f"**영상:** {video_title}")
                st.write(f"**영상 ID:** {v}")
                st.write(f"**계정:** {a}")
                st.write(f"**일시:** {at.replace('T', ' ')[:19]}")
        
                # 실제 게시 댓글
                st.markdown("**댓글 내용**")
                st.text_area(
                    "게시 댓글",
                    value=posted_comment or "댓글 기록 없음",
                    height=120,
                    disabled=True,
                    key=f"history_{v}_{a}_{at}"
                )
        
                # 결과 메시지
                st.caption(f"처리 결과: {message or '기록 없음'}")
        
                # YouTube 영상 링크
                st.link_button(
                    "YouTube 영상 확인",
                    f"https://www.youtube.com/watch?v={v}",
                    use_container_width=True
                )
        
                # 실패 캡처
                if shot:
                    screenshot_path = Path(shot)
        
                    if screenshot_path.is_file():
                        st.image(
                            str(screenshot_path),
                            caption="게시 시도 화면 캡처"
                        )
                    else:
                        st.caption(f"캡처 파일: {shot}")
