// Plain browser script (no imports/exports); types come from ../types.d.ts.

function el<T extends HTMLElement = HTMLElement>(id: string): T {
  return document.getElementById(id) as T;
}

let preview: PreviewData | null = null;
let folders = {} as Record<DownloadMode, string>;
const currentMode = () => el<HTMLSelectElement>('mode').value as DownloadMode;
let running = false;
let rows: HTMLLIElement[] = []; // <li> elements for the tracks being downloaded, in order
let lastFolder = '';

function showMessage(text: string): void {
  el('message').textContent = text;
  el('message').hidden = !text;
}

function fmtTime(seconds: number): string {
  const s = Math.round(seconds || 0);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

function trackBoxes(): HTMLInputElement[] {
  return [...document.querySelectorAll<HTMLInputElement>('#tracks input')];
}

function selectedIds(): string[] {
  return trackBoxes().filter((b) => b.checked).map((b) => b.dataset.id!);
}

function subBoxes(): HTMLInputElement[] {
  return [...document.querySelectorAll<HTMLInputElement>('#subsList input')];
}

function setRunning(value: boolean): void {
  running = value;
  for (const id of ['url', 'previewBtn', 'selectAll', 'mode', 'hevc', 'maxHeight', 'bitrate', 'enrich', 'folderBtn']) {
    el<HTMLInputElement>(id).disabled = value;
  }
  for (const box of [...trackBoxes(), ...subBoxes()]) box.disabled = value;
  el('subsBox').classList.toggle('disabled', value);
  if (value) el<HTMLDetailsElement>('subsBox').open = false;
  el('downloadBtn').hidden = value;
  el('cancelBtn').hidden = !value;
  el<HTMLButtonElement>('cancelBtn').disabled = false;
  el('cancelBtn').textContent = 'Cancel';
}

const STANDARD_HEIGHTS = [4320, 2160, 1440, 1080, 720, 480, 360];

/** Fills the resolution list: what a single video offers, or standard caps for a playlist. */
function fillHeights(heights: number[]): void {
  const select = el<HTMLSelectElement>('maxHeight');
  const previous = select.value;
  select.replaceChildren(new Option('Best available', ''));
  const playlist = heights.length === 0;
  for (const h of playlist ? STANDARD_HEIGHTS : heights) {
    select.append(new Option(playlist ? `${h}p or best below` : `${h}p`, String(h)));
  }
  select.value = [...select.options].some((o) => o.value === previous) ? previous : '';
}

/** Language codes the user wants; survives reloads so a choice is kept across links. */
let wantedLangs = new Set<string>();

/** Renders the subtitle checkboxes for what the loaded link offers. */
function fillSubtitles(options: SubtitleOption[], emptyText: string): void {
  const list = el('subsList');
  list.replaceChildren();
  for (const s of options) {
    const label = document.createElement('label');
    label.className = 'check';
    const box = document.createElement('input');
    box.type = 'checkbox';
    box.value = s.lang;
    box.checked = wantedLangs.has(s.lang);
    box.disabled = running;
    box.addEventListener('change', () => {
      if (box.checked) wantedLangs.add(s.lang);
      else wantedLangs.delete(s.lang);
      updateSubsSummary();
    });
    label.append(box, `${s.name} (${s.lang})${s.auto ? ' · auto-generated' : ''}`);
    list.append(label);
  }
  // Subtitles-only mode needs a language: offer English when nothing chosen applies
  const mode = el<HTMLSelectElement>('mode').value;
  const en = subBoxes().find((b) => b.value === 'en');
  if (mode === 'captions' && en && !subBoxes().some((b) => b.checked)) {
    en.checked = true;
    wantedLangs.add('en');
  }
  el('subsEmpty').textContent = emptyText;
  el('subsEmpty').hidden = !emptyText;
  updateSubsSummary();
}

/** The dropdown's closed label: the chosen languages, or a count when there are many. */
function updateSubsSummary(): void {
  const chosen = subBoxes().filter((b) => b.checked).map((b) => b.value);
  el('subsSummary').textContent = !chosen.length ? 'None'
    : chosen.length <= 3 ? chosen.join(', ') : `${chosen.length} languages`;
}

/** Shows only the options that apply to the chosen download mode. */
function applyMode(): void {
  const mode = el<HTMLSelectElement>('mode').value as DownloadMode;
  el('heightLabel').hidden = mode !== 'video';
  el('hevcLabel').hidden = mode !== 'video';
  el('bitrateLabel').hidden = mode === 'captions';
  el('enrichLabel').hidden = mode !== 'mp3';
  el('bitrateLabel').firstChild!.textContent = mode === 'video' ? 'Audio quality (MP3) ' : 'Audio quality ';
}

function updateCount(): void {
  if (!preview) return;
  const selected = selectedIds().length;
  el('listCount').textContent = `${selected} of ${preview.tracks.length} selected`;
  el<HTMLButtonElement>('downloadBtn').disabled = selected === 0;
}

function renderTracks(data: PreviewData): void {
  const ul = el('tracks');
  ul.replaceChildren();
  for (const t of data.tracks) {
    const li = document.createElement('li');

    const box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = true;
    box.dataset.id = t.video_id;
    box.setAttribute('aria-label', `${t.artist} - ${t.title}`);
    box.addEventListener('change', updateCount);

    const img = document.createElement('img');
    img.alt = '';
    img.loading = 'lazy';
    if (t.cover_url) img.src = t.cover_url;

    const meta = document.createElement('div');
    meta.className = 'meta';
    const title = document.createElement('div');
    title.className = 'title';
    title.textContent = t.title;
    const artist = document.createElement('div');
    artist.className = 'artist';
    artist.textContent = t.artist;
    meta.append(title, artist);

    const time = document.createElement('span');
    time.className = 'time';
    time.textContent = fmtTime(t.duration);
    const state = document.createElement('span');
    state.className = 'state';

    li.append(box, img, meta, time, state);
    ul.append(li);
  }
  el<HTMLInputElement>('selectAll').checked = true;
  el('listTitle').textContent = data.name || 'Video';
  el('listSection').hidden = false;
  updateCount();
}

let subsToken = 0; // identifies the latest Load, so a slow playlist scan can't overwrite a newer one

async function loadPreview(): Promise<void> {
  const url = el<HTMLInputElement>('url').value.trim();
  if (!url) return showMessage('Paste a YouTube link first.');
  showMessage('');
  el('progressSection').hidden = true;
  el<HTMLButtonElement>('previewBtn').disabled = true;
  el('previewBtn').textContent = 'Loading…';
  const result = await window.api.preview(url);
  el<HTMLButtonElement>('previewBtn').disabled = false;
  el('previewBtn').textContent = 'Load';
  if (result.error !== undefined) {
    el('listSection').hidden = true;
    return showMessage(result.error);
  }
  preview = result;
  fillHeights(result.heights);
  renderTracks(result);
  const token = ++subsToken;
  if (result.kind !== 'playlist') {
    fillSubtitles(result.subtitles, result.subtitles.length ? '' : 'This video has no subtitles.');
    return;
  }
  // A playlist's languages need every video's info: scan in the background
  fillSubtitles([], 'Checking which languages the videos offer…');
  const subs = await window.api.listSubtitles(url);
  if (token !== subsToken) return; // a newer Load replaced this one
  if ('error' in subs) fillSubtitles([], subs.error);
  else fillSubtitles(subs, subs.length ? '' : 'These videos have no subtitles.');
}

async function startDownload(): Promise<void> {
  const ids = selectedIds();
  if (!ids.length) return;
  const bitrate = el<HTMLSelectElement>('bitrate').value;
  const enrich = el<HTMLInputElement>('enrich').checked;
  const mode = el<HTMLSelectElement>('mode').value as DownloadMode;
  const maxHeight = el<HTMLSelectElement>('maxHeight').value;
  const hevc = el<HTMLInputElement>('hevc').checked;
  const subLangs = subBoxes().filter((b) => b.checked).map((b) => b.value);
  if (mode === 'captions' && !subLangs.length) return showMessage('Choose at least one subtitle language.');
  // wantedLangs also keeps earlier picks this link doesn't offer
  await window.api.saveSettings({ folders, bitrate, enrich, mode, hevc, maxHeight, subLangs: [...wantedLangs] });

  // Rows for the selected tracks, in download order (the backend keeps playlist order).
  const all = [...document.querySelectorAll<HTMLLIElement>('#tracks li')];
  rows = all.filter((li) => li.querySelector('input')!.checked);
  for (const li of all) {
    li.className = '';
    li.querySelector('.state')!.textContent = '';
  }

  el('log').textContent = '';
  el('summary').hidden = true;
  el('overallBar').style.width = '0';
  el('trackBar').style.width = '0';
  el('overallText').textContent = 'Starting…';
  el('trackText').textContent = '';
  el('progressSection').hidden = false;
  showMessage('');
  setRunning(true);

  const r = await window.api.startDownload({
    url: el<HTMLInputElement>('url').value.trim(), folder: folders[mode], bitrate, enrich, mode, hevc, maxHeight, subLangs, trackIds: ids,
  });
  if ('error' in r) {
    setRunning(false);
    showMessage(r.error);
  }
}

function setRowState(index: number, cls: string, text: string): void {
  const li = rows[index - 1];
  if (!li) return;
  li.className = cls;
  li.querySelector('.state')!.textContent = text;
  if (cls === 'active') li.scrollIntoView({ block: 'nearest' });
}

function onEvent(ev: BackendEvent): void {
  switch (ev.event) {
    case 'log': {
      const log = el('log');
      log.textContent += `${ev.message}\n`;
      log.scrollTop = log.scrollHeight;
      break;
    }
    case 'start':
      lastFolder = ev.folder;
      el('overallText').textContent = `0 of ${ev.total} done`;
      break;
    case 'track_start':
      setRowState(ev.index, 'active', 'Downloading');
      el('trackBar').style.width = '0';
      el('trackText').textContent = ev.label;
      el('overallText').textContent = `Video ${ev.index} of ${ev.total}`;
      el('overallBar').style.width = `${((ev.index - 1) / ev.total) * 100}%`;
      break;
    case 'progress':
      el('trackBar').style.width = `${ev.percent}%`;
      if (ev.converting) {
        setRowState(rows.findIndex((r) => r.className === 'active') + 1, 'active', 'Converting');
      }
      break;
    case 'track_done':
      setRowState(ev.index, 'done', 'Done');
      el('overallBar').style.width = `${(ev.index / rows.length) * 100}%`;
      break;
    case 'track_error':
      setRowState(ev.index, 'error', 'Failed');
      break;
    case 'done':
      finish(ev);
      break;
  }
}

function finish(summary: DoneEvent): void {
  setRunning(false);
  if (summary.folder) lastFolder = summary.folder;
  el('trackText').textContent = '';
  el('trackBar').style.width = '0';
  if (summary.error) {
    showMessage(summary.error);
    return;
  }
  const total = summary.ok.length + summary.failed.length;
  if (!summary.cancelled) el('overallBar').style.width = '100%';
  el('overallText').textContent = summary.cancelled ? 'Cancelled' : 'Finished';
  el('summaryText').textContent =
    `${summary.ok.length} of ${total} file(s) saved${summary.failed.length ? `, ${summary.failed.length} failed` : ''}.`;
  const failedList = el('failed');
  failedList.replaceChildren();
  for (const f of summary.failed) {
    const li = document.createElement('li');
    li.textContent = `${f.track}: ${f.error}`;
    failedList.append(li);
  }
  el('openBtn').hidden = !lastFolder;
  el('summary').hidden = false;
}

function showFolder(): void {
  const path = folders[currentMode()];
  el('folder').textContent = path;
  el('folder').title = path;
}

async function init(): Promise<void> {
  const s = await window.api.getSettings();
  folders = s.folders;
  el<HTMLSelectElement>('bitrate').value = s.bitrate;
  el<HTMLInputElement>('enrich').checked = s.enrich;
  el<HTMLSelectElement>('mode').value = s.mode;
  wantedLangs = new Set(s.subLangs);
  el<HTMLInputElement>('hevc').checked = s.hevc;
  fillHeights([]);
  fillSubtitles([], 'Load a link to see its subtitles.');
  el<HTMLSelectElement>('maxHeight').value = s.maxHeight;
  applyMode();
  showFolder();
  el('mode').addEventListener('change', () => { applyMode(); showFolder(); });
  // Close the subtitle dropdown on an outside click or Escape
  document.addEventListener('click', (e) => {
    const box = el<HTMLDetailsElement>('subsBox');
    if (box.open && !box.contains(e.target as Node)) box.open = false;
  });
  document.addEventListener('keydown', (e) => {
    if ((e as KeyboardEvent).key === 'Escape') el<HTMLDetailsElement>('subsBox').open = false;
  });

  el('previewBtn').addEventListener('click', loadPreview);
  el('url').addEventListener('keydown', (e) => {
    if ((e as KeyboardEvent).key === 'Enter' && !running) loadPreview();
  });
  el('selectAll').addEventListener('change', (e) => {
    const checked = (e.target as HTMLInputElement).checked;
    for (const box of trackBoxes()) box.checked = checked;
    updateCount();
  });
  el('folderBtn').addEventListener('click', async () => {
    const picked = await window.api.pickFolder(folders[currentMode()]);
    if (picked) { folders[currentMode()] = picked; showFolder(); }
  });
  el('downloadBtn').addEventListener('click', startDownload);
  el('cancelBtn').addEventListener('click', () => {
    el<HTMLButtonElement>('cancelBtn').disabled = true;
    el('cancelBtn').textContent = 'Cancelling…';
    window.api.cancelDownload();
  });
  el('openBtn').addEventListener('click', () => window.api.openFolder(lastFolder));
  window.api.onEvent(onEvent);
}

init();
