"use strict";

const $ = (id) => document.getElementById(id);
const audio = $("audio");
const storagePrefix = `ebs-study:${location.pathname}:`;
const state = { episodes: [], selected: null, course: "all", query: "", readyOnly: false, loading: false, lessonJSON: "", lastSaved: 0 };
const escapeHTML = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character]));
const storage = {
  get(key) { try { return localStorage.getItem(storagePrefix + key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(storagePrefix + key, String(value)); } catch { /* Playback also works without storage. */ } },
};
function notify(message) {
  $("notice").textContent = message;
  $("notice").hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { $("notice").hidden = true; }, 5000);
}
function dateLabel(value) {
  const date = new Date(`${value}T12:00:00`);
  return Number.isNaN(date.getTime()) ? value : `${date.getMonth() + 1}월 ${date.getDate()}일 (${["일", "월", "화", "수", "목", "금", "토"][date.getDay()]})`;
}
function timestampSeconds(value) {
  const match = /^\[?(\d{2}):([0-5]\d):([0-5]\d)\]?$/.exec(value || "");
  return match ? Number(match[1]) * 3600 + Number(match[2]) * 60 + Number(match[3]) : null;
}
function filteredEpisodes() {
  const query = state.query.toLocaleLowerCase().replace(/\s/g, "");
  return state.episodes.filter((episode) =>
    (state.course === "all" || episode.course === state.course) &&
    (!state.readyOnly || episode.study) &&
    (!query || [episode.date, episode.date.replace(/-/g, ""), dateLabel(episode.date), episode.course,
      episode.study?.episode_title, ...(episode.study?.topics || [])].join(" ").toLocaleLowerCase().replace(/\s/g, "").includes(query))
  );
}
function renderLibrary() {
  const episodes = filteredEpisodes();
  $("library-count").textContent = `${episodes.length}회`;
  $("episode-list").innerHTML = episodes.length ? episodes.map((episode) => `<button class="episode-item" type="button" data-episode="${escapeHTML(episode.id)}" aria-current="${episode.id === state.selected}"><span class="episode-date">${escapeHTML(dateLabel(episode.date))}<span class="episode-course">${episode.course === "초급일본어" ? "초급" : "중급"}</span></span><span class="episode-topic">${episode.study ? '<span class="note-dot" aria-hidden="true"></span>' : ""}${escapeHTML(episode.study?.episode_title || "방송 녹음")}</span></button>`).join("") : '<p class="library-footnote">검색 조건에 맞는 방송이 없습니다.</p>';
  $("episode-select").innerHTML = episodes.length ? episodes.map((episode) => `<option value="${escapeHTML(episode.id)}">${escapeHTML(dateLabel(episode.date))} · ${escapeHTML(episode.course)}${episode.study ? " · 학습노트 ✓" : ""}</option>`).join("") : '<option value="">검색 결과 없음</option>';
  if (episodes.length && !episodes.some((episode) => episode.id === state.selected)) $("episode-select").insertAdjacentHTML("afterbegin", '<option value="" disabled>검색 결과에서 방송 선택</option>');
  $("episode-select").disabled = !episodes.length;
  $("episode-select").value = state.selected || "";
}
function renderLesson(episode) {
  const serialized = JSON.stringify(episode);
  if (serialized === state.lessonJSON) return;
  state.lessonJSON = serialized;
  const study = episode.study;
  const header = `<header class="lesson-header"><div class="lesson-meta"><span class="course-badge">${escapeHTML(episode.course)}</span><span>${escapeHTML(episode.date)} · ${escapeHTML(episode.time)}</span></div><p class="eyebrow">DAILY LISTENING NOTE</p><h2 lang="${study ? "ja" : "ko"}">${escapeHTML(study?.episode_title || `${dateLabel(episode.date)} 일본어 방송`)}</h2>${study ? `<div class="topics">${study.topics.map((topic) => `<span class="topic" lang="ja">${escapeHTML(topic)}</span>`).join("")}</div>` : '<p class="lesson-description">아래 재생 버튼으로 오늘 방송을 들어보세요.</p>'}</header>`;
  if (!study) {
    const hasReady = state.episodes.some((item) => item.study);
    $("lesson").innerHTML = `${header}<section class="empty-state"><p class="eyebrow">LISTEN FIRST</p><h3>학습노트가 아직 준비되지 않았어요.</h3><p>녹음은 지금 들을 수 있습니다.<br>요약과 단어는 분석이 완료되면 이 화면에 나타납니다.</p>${hasReady ? '<button class="quiet-button" type="button" id="show-ready">완성된 학습노트 보기 →</button>' : ""}</section>`;
    return;
  }
  $("lesson").innerHTML = `${header}<section class="summary-card" aria-label="방송 요약"><p class="card-kicker">THE ESSENTIALS</p><h3>오늘의 이야기</h3><p class="summary-text">${escapeHTML(study.summary_ko).replace(/\n/g, "<br>")}</p></section><section aria-label="주요 어휘"><div class="vocab-heading"><h3>기억할 단어와 표현</h3><span class="count">${study.vocabulary.length}개</span></div><p class="vocab-help">시간 버튼을 누르면 해당 표현이 나오는 부분을 들을 수 있어요.</p>${study.vocabulary.map((item, index) => {
    const seconds = timestampSeconds(item.timestamp);
    return `<article class="word-card"><div class="word-top"><div class="word-label"><span class="word-number">${String(index + 1).padStart(2, "0")}</span><strong class="word-ja" lang="ja">${escapeHTML(item.word)}</strong><span class="reading" lang="ja">${escapeHTML(item.reading)}</span></div>${seconds !== null ? `<button class="timestamp" type="button" data-seconds="${seconds}" aria-label="${escapeHTML(item.word)} 녹음 ${escapeHTML(item.timestamp)}부터 재생">▶ ${escapeHTML(item.timestamp.replace(/^\[|\]$/g, ""))}</button>` : ""}</div><p class="meaning">${escapeHTML(item.meaning_ko)}${item.part_of_speech ? `<span class="pos" lang="ja">${escapeHTML(item.part_of_speech)}</span>` : ""}</p><div class="sentence"><p class="sentence-ja" lang="ja">${escapeHTML(item.source_sentence_ja)}</p><p class="sentence-ko">${escapeHTML(item.sentence_ko)}</p></div></article>`;
  }).join("")}</section>`;
}
function saveProgress() {
  if (state.selected && audio.readyState >= 1 && Number.isFinite(audio.currentTime)) storage.set(`progress:${state.selected}`, audio.currentTime);
}
function selectEpisode(id, updateHash = true) {
  const episode = state.episodes.find((item) => item.id === id);
  if (!episode) return;
  if (state.selected !== id) {
    saveProgress();
    audio.pause();
    state.selected = id;
    audio.src = episode.audio_url;
    audio.playbackRate = Number(storage.get("speed")) || 1;
    $("speed").value = String(audio.playbackRate);
    $("player").hidden = false;
    $("player-title").textContent = `${dateLabel(episode.date)} · ${episode.course}`;
    $("player-subtitle").textContent = "듣던 위치에서 이어집니다";
    if ("mediaSession" in navigator && "MediaMetadata" in window) {
      navigator.mediaSession.metadata = new MediaMetadata({ title: episode.study?.episode_title || `${episode.date} ${episode.course}`, artist: "EBS 일본어", album: "오늘 일본어" });
    }
  }
  storage.set("selected", id);
  storage.set("latest", state.episodes[0]?.id || "");
  // Keep the home-screen bookmark on the library URL so tomorrow's recording
  // can be selected automatically. Incoming episode links still work once.
  if (updateHash) history.replaceState(null, "", location.pathname + location.search);
  renderLibrary();
  renderLesson(episode);
}
async function loadLibrary(manual = false) {
  if (state.loading) return;
  state.loading = true;
  $("refresh").disabled = true;
  try {
    const response = await fetch(`data.json?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data.episodes) || !data.episodes.length) throw new Error("No episodes");
    const oldLatest = state.episodes[0]?.id;
    state.episodes = data.episodes;
    if (!state.selected) {
      const hash = decodeURIComponent(location.hash.slice(1));
      const saved = storage.get("latest") === data.episodes[0].id ? storage.get("selected") : null;
      selectEpisode(data.episodes.some((item) => item.id === hash) ? hash : data.episodes.some((item) => item.id === saved) ? saved : data.episodes[0].id);
    } else {
      const selected = data.episodes.find((item) => item.id === state.selected);
      if (selected) { renderLibrary(); renderLesson(selected); }
      else selectEpisode(data.episodes[0].id);
      if (oldLatest && oldLatest !== data.episodes[0].id) notify("새 방송이 추가됐어요. 보관함에서 선택해 주세요.");
    }
    $("updated-at").textContent = `갱신 ${new Date(data.updated_at).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}`;
    if (manual && audio.error) audio.load();
    if (manual) notify("최신 방송과 학습노트를 확인했어요.");
  } catch (error) {
    if (!state.episodes.length) $("lesson").innerHTML = '<section class="empty-state"><h2>학습노트에 연결할 수 없어요.</h2><p>맥이 켜져 있고 아이폰이 같은 Wi-Fi에 연결되어 있는지 확인한 뒤 새로고침해 주세요.</p></section>';
    if (manual || !state.episodes.length) notify("연결을 확인한 뒤 다시 시도해 주세요.");
    console.warn("Study library could not be refreshed", error);
  } finally { state.loading = false; $("refresh").disabled = false; }
}
function applyFilters(selectFirst = true) {
  renderLibrary();
  const episodes = filteredEpisodes();
  if (selectFirst && episodes.length && !episodes.some((episode) => episode.id === state.selected)) selectEpisode(episodes[0].id);
}
document.querySelectorAll("[data-course]").forEach((button) => button.addEventListener("click", () => {
  state.course = button.dataset.course;
  document.querySelectorAll("[data-course]").forEach((item) => item.setAttribute("aria-pressed", String(item === button)));
  applyFilters();
}));
$("search").addEventListener("input", (event) => { state.query = event.target.value.trim(); applyFilters(false); });
$("ready-only").addEventListener("change", (event) => { state.readyOnly = event.target.checked; applyFilters(); });
$("filters-toggle").addEventListener("click", () => {
  const expanded = $("filters-toggle").getAttribute("aria-expanded") !== "true";
  $("filters-toggle").setAttribute("aria-expanded", String(expanded));
  $("search-options").classList.toggle("expanded", expanded);
});
$("episode-select").addEventListener("change", (event) => selectEpisode(event.target.value));
$("episode-list").addEventListener("click", (event) => { const button = event.target.closest("[data-episode]"); if (button) selectEpisode(button.dataset.episode); });
$("lesson").addEventListener("click", (event) => {
  if (event.target.closest("#show-ready")) { $("ready-only").checked = true; state.readyOnly = true; state.query = ""; $("search").value = ""; state.course = "all"; document.querySelectorAll("[data-course]").forEach((item) => item.setAttribute("aria-pressed", String(item.dataset.course === "all"))); applyFilters(); }
  const button = event.target.closest("[data-seconds]");
  if (!button) return;
  const seconds = Number(button.dataset.seconds);
  if (Number.isFinite(audio.duration) && seconds >= audio.duration) { notify("이 시간은 녹음 길이를 벗어납니다."); return; }
  const seek = () => { audio.currentTime = seconds; };
  if (audio.readyState >= 1) seek(); else audio.addEventListener("loadedmetadata", seek, { once: true });
  audio.play().catch(() => notify("아래 재생 버튼을 누르면 선택한 위치에서 들을 수 있어요."));
});
audio.addEventListener("loadedmetadata", () => {
  const saved = Number(storage.get(`progress:${state.selected}`));
  if (saved > 0 && Number.isFinite(audio.duration) && saved < audio.duration - 3) audio.currentTime = saved;
  audio.playbackRate = Number(storage.get("speed")) || 1;
});
audio.addEventListener("timeupdate", () => { if (Date.now() - state.lastSaved > 2000) { saveProgress(); state.lastSaved = Date.now(); } });
audio.addEventListener("pause", saveProgress);
audio.addEventListener("ended", () => storage.set(`progress:${state.selected}`, 0));
audio.addEventListener("error", () => notify("녹음을 불러오지 못했어요. 연결을 확인하고 새로고침해 주세요."));
$("speed").addEventListener("change", (event) => { audio.playbackRate = Number(event.target.value); storage.set("speed", audio.playbackRate); });
$("rewind").addEventListener("click", () => { audio.currentTime = Math.max(0, audio.currentTime - 10); });
$("refresh").addEventListener("click", () => loadLibrary(true));
window.addEventListener("pagehide", saveProgress);
window.addEventListener("hashchange", () => { const id = decodeURIComponent(location.hash.slice(1)); selectEpisode(id, false); });
document.addEventListener("visibilitychange", () => { if (!document.hidden) loadLibrary(); else saveProgress(); });
setInterval(() => { if (!document.hidden) loadLibrary(); }, 60000);
loadLibrary();
