
const $ = (selector) => document.querySelector(selector);
const script = $('#script');
const highlights = $('#highlights');
const search = $('#search');
const toast = $('#toast');
const app = $('.app');
const mobileLayout = window.matchMedia('(max-width: 800px)');
const mobileTabs = [...document.querySelectorAll('.mobile-tab[data-mobile-view]')];
const toolbar = $('.toolbar');
const readerSettings = $('#reader-settings');
const readerSettingsToggle = $('#reader-settings-toggle');
const audioPlayer = $('#audio-player');
let state = {};
let textTimer;
let lastActiveRange = '';
let highlightRenderFrame;
const remoteMode = ['http:', 'https:'].includes(window.location.protocol);
let audioQueue = [];
let audioPlaying = false;
let currentAudio = null;
let audioEpoch = 0;
let audioPrimed = false;
let audioStartNeedsGesture = false;
let silentAudioUrl = null;
let pendingHlsStream = null;
let hlsGeneration = 0;
let selectedHlsTransport = null;
let hlsPlayer = null;

function getAudioClientId() {
  if (!remoteMode) return 'desktop-preview';
  const storageKey = 'voice-reader-audio-client-id';
  try {
    let clientId = sessionStorage.getItem(storageKey);
    if (!clientId) {
      clientId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
      sessionStorage.setItem(storageKey, clientId);
    }
    return clientId;
  } catch (_) {
    return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  }
}

const audioClientId = getAudioClientId();

function hlsLog(message, details = {}) {
  console.info(`[HLS] ${message}`, {
    ...details,
    url: window.location.href,
    userAgent: navigator.userAgent,
  });
}

function hlsError(message, error, details = {}) {
  console.error(`[HLS] ${message}`, {
    ...details,
    error: error?.message || String(error || 'unknown error'),
    mediaErrorCode: audioPlayer.error?.code,
    mediaErrorMessage: audioPlayer.error?.message,
    networkState: audioPlayer.networkState,
    readyState: audioPlayer.readyState,
    src: audioPlayer.currentSrc || audioPlayer.src,
  });
}

function setMediaSessionPlaybackState(playbackState) {
  if (!remoteMode || !('mediaSession' in navigator)) return;
  try { navigator.mediaSession.playbackState = playbackState; }
  catch (_) { /* The API is optional and varies between mobile browsers. */ }
}

function updateMediaSessionPosition() {
  if (!remoteMode || !currentAudio || !('mediaSession' in navigator) || !Number.isFinite(audioPlayer.duration) || audioPlayer.duration <= 0) return;
  try {
    navigator.mediaSession.setPositionState({
      duration: audioPlayer.duration,
      position: Math.min(audioPlayer.currentTime, audioPlayer.duration),
      playbackRate: audioPlayer.playbackRate,
    });
  } catch (_) { /* Position controls are not available in every browser. */ }
}

function updateMediaSession() {
  if (!remoteMode || !('mediaSession' in navigator)) return;
  try {
    if (typeof MediaMetadata !== 'undefined') {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: state.highlighted_text?.trim() || 'Voice Reader',
        artist: state.voice?.trim() || 'Voice Reader',
        album: 'Voice Reader',
        artwork: [{
          src: new URL('/icon/icon.png', window.location.href).href,
          sizes: '650x650',
          type: 'image/png',
        }],
      });
    }
    const stopped = !state.playback_mode && !audioPlaying && !currentAudio
      && ['Idle', 'Stopped', 'Web interface ready'].includes(state.status);
    setMediaSessionPlaybackState(stopped ? 'none' : (audioPlaying || state.playback_mode ? 'playing' : 'paused'));
    updateMediaSessionPosition();
  } catch (_) { /* Media Session support is best-effort. */ }
}

function seekCurrentAudio(offset) {
  if (!Number.isFinite(audioPlayer.duration)) return;
  audioPlayer.currentTime = Math.max(0, Math.min(audioPlayer.duration, audioPlayer.currentTime + offset));
  updateMediaSessionPosition();
}

function setMediaSessionAction(action, handler) {
  try { navigator.mediaSession.setActionHandler(action, handler); }
  catch (_) { /* Ignore actions that this browser has not implemented. */ }
}

function configureMediaSession() {
  if (!remoteMode || !('mediaSession' in navigator)) return;
  setMediaSessionAction('play', () => { void control('play'); });
  setMediaSessionAction('pause', () => { void control('pause'); });
  setMediaSessionAction('stop', () => { void control('stop'); });
  setMediaSessionAction('previoustrack', () => { void control('back'); });
  setMediaSessionAction('nexttrack', () => { void control('forward'); });
  setMediaSessionAction('seekbackward', (details = {}) => seekCurrentAudio(-(details.seekOffset || 10)));
  setMediaSessionAction('seekforward', (details = {}) => seekCurrentAudio(details.seekOffset || 10));
  setMediaSessionAction('seekto', (details = {}) => {
    if (!Number.isFinite(details.seekTime) || !Number.isFinite(audioPlayer.duration)) return;
    audioPlayer.currentTime = Math.max(0, Math.min(audioPlayer.duration, details.seekTime));
    updateMediaSessionPosition();
  });
  updateMediaSession();
}

async function remoteRequest(path, payload) {
  const response = await fetch(path, payload && {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || 'The reader did not accept the command.');
  return result;
}

async function remoteCall(method, ...args) {
  if (method === 'get_state') return remoteRequest('/api/state');
  if (method === 'control') return remoteRequest('/api/control', { action: args[0], ...(args[1] !== undefined ? { text: args[1] } : {}) });
  if (method === 'set_audio_capabilities') return remoteRequest('/api/audio-capabilities', {
    hls: Boolean(args[0]),
    client_id: audioClientId,
  });
  if (method === 'read_clipboard') {
    try { return await readBrowserClipboard(); }
    catch (_) {
      const result = await remoteRequest('/api/ui', { action: 'paste_desktop_clipboard' });
      return { ...result, source: 'desktop' };
    }
  }
  if (method === 'characters') return (await remoteRequest('/api/state')).characters;
  const actions = {
    set_text: { action: 'set_text', text: args[0] },
    set_speed: { action: 'set_speed', value: args[0] },
    change_font_size: { action: 'change_font_size', delta: args[0] },
    set_mode: { action: 'set_mode', dialog_mode: args[0] },
    select_character: { action: 'select_character', name: args[0] },
    add_character: { action: 'add_character' },
    delete_character: { action: 'delete_character', name: args[0] },
    rename_character: { action: 'rename_character', old_name: args[0], new_name: args[1] },
    update_character: { action: 'update_character', name: args[0], voice: args[1], speed: args[2], volume: args[3] },
    toggle_server: { action: 'toggle_server' },
  };
  if (!actions[method]) throw new Error('The shared reader does not support this action.');
  return remoteRequest('/api/ui', actions[method]);
}

async function readBrowserClipboard() {
  if (navigator.clipboard?.read) {
    const items = await navigator.clipboard.read();
    let text = '';
    let html = '';
    for (const item of items) {
      if (!html && item.types.includes('text/html')) html = await (await item.getType('text/html')).text();
      if (!text && item.types.includes('text/plain')) text = await (await item.getType('text/plain')).text();
      if (html && text) break;
    }
    if (html || text) return { ok: true, text, ...(html ? { html } : {}) };
  }
  return { ok: true, text: await navigator.clipboard.readText() };
}

function bridge(method, ...args) {
  if (remoteMode) return remoteCall(method, ...args);
  if (!window.pywebview?.api?.[method]) return Promise.reject(new Error('The desktop bridge is unavailable.'));
  return window.pywebview.api[method](...args);
}

async function applyDesktopColorScheme() {
  if (remoteMode) return;
  try {
    const { theme } = await bridge('get_color_scheme');
    if (theme === 'dark' || theme === 'light') document.documentElement.dataset.colorScheme = theme;
  } catch (_) {
    // The browser's prefers-color-scheme result remains the fallback.
  }
}

function notify(message, error = false) {
  toast.textContent = message;
  toast.classList.toggle('error', error);
  toast.classList.add('show');
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => toast.classList.remove('show'), 3400);
}

function escapeHtml(value) {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
}

function richClipboardToText(html, fallback = '') {
  if (!html || typeof DOMParser === 'undefined') return fallback;
  const documentFragment = new DOMParser().parseFromString(html, 'text/html');
  const blockTags = new Set([
    'ADDRESS', 'ARTICLE', 'ASIDE', 'BLOCKQUOTE', 'DD', 'DIV', 'DL', 'DT',
    'FIGCAPTION', 'FIGURE', 'FOOTER', 'FORM', 'H1', 'H2', 'H3', 'H4', 'H5',
    'H6', 'HEADER', 'HR', 'LI', 'MAIN', 'NAV', 'OL', 'P', 'PRE', 'SECTION',
    'TABLE', 'TR', 'UL',
  ]);
  const ignoredTags = new Set(['HEAD', 'SCRIPT', 'STYLE', 'TEMPLATE']);
  let output = '';

  const addBreak = (count = 1) => {
    output = output.replace(/[ \t]+$/u, '');
    const existing = output.match(/\n*$/u)[0].length;
    output += '\n'.repeat(Math.max(0, count - existing));
  };
  const walk = (node) => {
    if (node.nodeType === 3) {
      output += node.nodeValue.replaceAll('\u00a0', ' ');
      return;
    }
    if (node.nodeType !== 1) return;
    const tag = node.tagName;
    if (ignoredTags.has(tag)) return;
    if (tag === 'BR') {
      addBreak();
      return;
    }
    if (tag === 'IMG') {
      output += node.getAttribute('alt') || '';
      return;
    }
    if (tag === 'TD' || tag === 'TH') {
      if (output && !output.endsWith('\n')) output += '; ';
      node.childNodes.forEach(walk);
      return;
    }
    const isBlock = blockTags.has(tag);
    if (isBlock) addBreak(2);
    node.childNodes.forEach(walk);
    if (isBlock) addBreak(2);
  };

  documentFragment.body.childNodes.forEach(walk);
  const structuredText = output
    .replace(/\r\n?/gu, '\n')
    .replace(/[ \t]+\n/gu, '\n')
    .replace(/\n[ \t]+/gu, '\n')
    .replace(/\n{3,}/gu, '\n\n')
    .trim();
  return structuredText || fallback;
}

function offsetsForLines(range) {
  if (!range?.start_line || !range?.end_line) return null;
  const lines = script.value.split('\n');
  const startLine = Math.max(1, range.start_line);
  const endLine = Math.min(lines.length, range.end_line);
  if (startLine > lines.length || endLine < startLine) return null;
  let start = 0;
  for (let index = 0; index < startLine - 1; index += 1) start += lines[index].length + 1;
  let end = start;
  for (let index = startLine - 1; index < endLine; index += 1) {
    end += lines[index].length;
    if (index < endLine - 1) end += 1;
  }
  return { start, end };
}

function syncHighlightMetrics() {
  const style = window.getComputedStyle(script);
  const properties = [
    'fontFamily', 'fontSize', 'fontWeight', 'fontStyle', 'fontVariant',
    'lineHeight', 'letterSpacing', 'wordSpacing', 'textIndent',
    'textTransform', 'tabSize', 'whiteSpace', 'overflowWrap', 'wordBreak',
    'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
  ];

  for (const property of properties) highlights.style[property] = style[property];

  // A textarea's scrollbars reduce its text area. Measure the live content
  // box so the highlight layer wraps at exactly the same character.
  highlights.style.width = `${script.clientWidth}px`;
  highlights.style.height = `${script.clientHeight}px`;
}

function renderHighlights() {
  const ranges = [
    { ...offsetsForLines(state.generation_lines), type: 'generation', rank: 3 },
    { ...offsetsForLines(state.seek_lines), type: 'seek', rank: 2 },
    { ...offsetsForLines(state.playing_lines), type: 'playing', rank: 1 },

  ].filter((range) => Number.isFinite(range.start) && range.end > range.start)
    .sort((a, b) => a.start - b.start || a.rank - b.rank);

  syncHighlightMetrics();
  let cursor = 0;
  let markup = '';
  for (const range of ranges) {
    if (range.start < cursor) continue;
    markup += escapeHtml(script.value.slice(cursor, range.start));
    markup += `<mark class="${range.type}">${escapeHtml(script.value.slice(range.start, range.end))}</mark>`;
    cursor = range.end;
  }
  highlights.innerHTML = markup + escapeHtml(script.value.slice(cursor)) + '\n';
  highlights.scrollTop = script.scrollTop;
  highlights.scrollLeft = script.scrollLeft;
  scrollToActiveHighlight();
}

function scrollToActiveHighlight() {
  const active = state.seek_lines || state.playing_lines;
  const key = active ? `${active.start_line}:${active.end_line}` : '';
  if (!key || key === lastActiveRange) { lastActiveRange = key; return; }
  lastActiveRange = key;
  const mark = highlights.querySelector('mark.seek, mark.playing');
  if (!mark) return;
  const top = mark.offsetTop;
  const bottom = top + mark.offsetHeight;
  // if (top < script.scrollTop || bottom > script.scrollTop + script.clientHeight) {
  script.scrollTop = Math.max(0, bottom - (script.clientHeight - mark.offsetHeight) / 2);
  // }
}

function setOptions(select, values, selected) {
  select.replaceChildren(...values.map((value) => {
    const option = document.createElement('option'); option.value = value; option.textContent = value; option.selected = value === selected; return option;
  }));
}

function renderCharacters(chars = state.characters || {}) {
  const selected = chars.selected;
  const items = chars.items || [];
  setOptions($('#character-list'), items.map((item) => item.name), selected);
  const current = items.find((item) => item.name === selected) || items[0];
  const dialog = Boolean(state.dialog_mode);
  $('#characters-title').textContent = dialog ? 'Character Voices' : 'Reader Voice';
  $('#character-actions').hidden = !dialog;
  $('#name-property').hidden = !dialog;
  $('#character-name').disabled = !current || !dialog;
  $('#character-voice').disabled = !current;
  $('#character-speed').disabled = !current;
  $('#character-volume').disabled = !current;
  setOptions($('#character-voice'), chars.voice_options || [], current?.voice);
  $('#character-name').value = current?.name || '';
  $('#character-speed').value = current?.speed ?? '';
  $('#character-volume').value = current?.volume ?? '';
}

function applyState(next) {
  state = next || {};
  if (document.activeElement !== script && typeof state.text === 'string') script.value = state.text;
  $('#status').textContent = state.status || 'Idle';
  $('#status').title = state.status || 'Idle';
  $('#speed').value = state.speed ?? 0.9;
  $('#speed-value').textContent = `${Number(state.speed ?? .9).toFixed(2)}x`;
  $('#mode').value = state.dialog_mode ? 'dialog' : 'reader';
  $('#mode').disabled = Boolean(state.playback_mode);
  updatePlayPause(Boolean(state.playback_mode));
  const size = state.font_size || 12;
  script.style.fontSize = `${size}px`; highlights.style.fontSize = `${size}px`;
  document.querySelectorAll('[data-font-size]').forEach((element) => { element.textContent = `${size}px`; });
  const server = state.server || {};
  const activeHls = state.audio || {};
  if (remoteMode && activeHls.hls_url) {
    queueHlsStream(activeHls.hls_url, activeHls.hls_generation);
  }
  const remoteSession = Boolean(server.remote);
  $('#server-toggle .button-label').textContent = remoteSession ? 'Web' : (server.running ? 'Stop' : 'Start');

  if (remoteSession) {
    $('#server-panel').hidden = true;
  }

  $('#server-toggle').classList.toggle('danger', Boolean(server.running));
  $('#server-toggle').classList.toggle('primary', !server.running && !remoteSession);
  $('#server-toggle').disabled = remoteSession;
  $('#server-port').disabled = Boolean(server.running) || remoteSession;
  if (server.port) $('#server-port').value = server.port;
  $('#server-message').textContent = server.message || '';
  const url = $('#server-url'); url.textContent = server.url || ''; url.href = server.url || '#';
  renderCharacters();
  renderHighlights();
  updateMediaSession();
  requestAnimationFrame(syncReaderSettingsLayout);
}

window.VoiceReaderDesktop = { applyState };

async function control(action) {
  try {
    if (remoteMode && action === 'play') {
      hlsLog('user pressed Play', {
        pendingStream: pendingHlsStream?.url || null,
        nativeHls: supportsNativeHls(),
        selectedHlsTransport,
      });
      audioStartNeedsGesture = false;
      // HLS must be loaded and played in this exact tap. The desktop receives
      // the control request only afterwards, then creates the stream that the
      // stable /api/hls/live playlist endpoint waits for.
      if (selectedHlsTransport) {
        audioPrimed = true;
        void startPendingHlsStream();
      } else {
        // WAV clips are created after this request reaches the desktop, so
        // retain a silent loop to preserve this media element's authorization.
        void unlockAudio().then(() => {
          audioPrimed = true;
          void playNextAudio();
        }).catch((error) => {
          hlsError('the silent audio unlock failed', error);
          audioPrimed = false;
          audioStartNeedsGesture = true;
          notify(`Audio needs a tap to start: ${error?.message || 'playback was blocked.'}`, true);
        });
      }
    }
    const result = await bridge('control', action, script.value);
    if (!result.ok) notify(result.message || 'The command could not be completed.', true);
  } catch (error) { notify(error.message, true); }
}

function updatePlayPause(isPlaying) {
  const button = $('#play-pause');
  const label = isPlaying ? 'Pause' : 'Play';
  const icon = button.querySelector('.ph');
  icon.classList.toggle('ph-play', !isPlaying);
  icon.classList.toggle('ph-pause', isPlaying);
  button.querySelector('.button-label').textContent = label;
  button.title = label;
  button.setAttribute('aria-label', label);
}

async function unlockAudio() {
  // Mobile browsers require the media element to begin playback from a
  // user gesture. Keep this exact element playing a silent loop until a
  // generated clip arrives; pausing it here can make the real clip fail
  // the browser's autoplay policy.
  await keepAudioSessionAlive();
}

function getSilentAudioUrl() {
  if (silentAudioUrl) return silentAudioUrl;
  const frames = 800;
  const bytes = new Uint8Array(44 + frames).fill(128, 44);
  const view = new DataView(bytes.buffer);
  const writeText = (offset, text) => [...text].forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)));
  writeText(0, 'RIFF'); view.setUint32(4, 36 + frames, true); writeText(8, 'WAVE');
  writeText(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 8000, true); view.setUint32(28, 8000, true); view.setUint16(32, 1, true); view.setUint16(34, 8, true);
  writeText(36, 'data'); view.setUint32(40, frames, true);
  silentAudioUrl = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }));
  return silentAudioUrl;
}

async function keepAudioSessionAlive() {
  const silentUrl = getSilentAudioUrl();
  if (audioPlayer.src !== silentUrl || !audioPlayer.loop) {
    audioPlayer.loop = true;
    audioPlayer.src = silentUrl;
    audioPlayer.load();
  }
  await audioPlayer.play();
}

function resetAudioPlayer() {
  destroyHlsPlayer();
  currentAudio = null;
  audioPlaying = false;
  audioPlayer.loop = false;
  audioPlayer.pause();
  audioPlayer.removeAttribute('src');
  audioPlayer.load();
}

function supportsNativeHls() {
  const supported = [
    'application/vnd.apple.mpegurl',
    'application/x-mpegURL',
    'application/x-mpegurl',
    'audio/mpegurl',
    'audio/x-mpegurl',
  ].some((mimeType) => Boolean(audioPlayer.canPlayType(mimeType)));
  return supported;
}

function isMobileDevice() {
  return /Android|iPhone|iPad|iPod|IEMobile|Opera Mini/i.test(navigator.userAgent)
    || (navigator.maxTouchPoints > 1 && window.matchMedia('(pointer: coarse)').matches);
}

function supportsMseHls() {
  return Boolean(window.Hls && window.Hls.isSupported());
}

function getHlsTransport() {
  if (supportsNativeHls()) return 'native';
  if (supportsMseHls()) return 'mse';
  return null;
}

function shouldUseHls() {
  // A device may use HLS only if this page has an actual implementation for
  // it: the native media element or the bundled Media Source player. Device
  // type alone cannot decode a playlist.
  return getHlsTransport() !== null;
}

function liveHlsUrl() {
  return new URL('/api/hls/live/playlist.m3u8', window.location.href).href;
}

function destroyHlsPlayer() {
  if (!hlsPlayer) return;
  try { hlsPlayer.destroy(); }
  catch (error) { hlsError('could not destroy the Media Source HLS player', error); }
  hlsPlayer = null;
}

function prepareHlsStream(item) {
  if (item.prepared) return true;
  const transport = item.player || getHlsTransport();
  if (!transport) {
    hlsLog('ignored an HLS stream because this browser has no HLS implementation', { streamUrl: item.url });
    return false;
  }

  item.player = transport;
  audioPlayer.loop = false;
  audioPlayer.volume = 1;
  if (transport === 'native') {
    audioPlayer.src = item.url;
    audioPlayer.load();
    item.prepared = true;
    hlsLog('prepared the native HLS media source', { streamUrl: item.url });
    return true;
  }

  destroyHlsPlayer();
  const player = new window.Hls({
    enableWorker: true,
    liveSyncDurationCount: 3,
    maxBufferLength: 90,
  });
  hlsPlayer = player;
  player.on(window.Hls.Events.MEDIA_ATTACHED, () => {
    hlsLog('Media Source attached; loading HLS playlist', { streamUrl: item.url });
    player.loadSource(item.url);
  });
  player.on(window.Hls.Events.MANIFEST_PARSED, (_, data) => {
    hlsLog('Media Source parsed the HLS playlist', { streamUrl: item.url, levels: data.levels?.length || 0 });
  });
  player.on(window.Hls.Events.ERROR, (_, data) => {
    hlsError('Media Source HLS player error', data?.error || data?.details, {
      streamUrl: item.url,
      type: data?.type,
      details: data?.details,
      fatal: data?.fatal,
      responseCode: data?.response?.code,
    });
    if (data?.fatal) failAudio(item, data?.error || new Error(data?.details || 'fatal HLS player error'));
  });
  player.attachMedia(audioPlayer);
  item.prepared = true;
  hlsLog('prepared the Media Source HLS player', { streamUrl: item.url });
  return true;
}

function queueHlsStream(url, generation = hlsGeneration) {
  if (Number.isFinite(generation) && generation < hlsGeneration) return;
  if (Number.isFinite(generation)) hlsGeneration = generation;
  const streamUrl = new URL(url, window.location.href).href;
  if (currentAudio?.transport === 'hls' && (currentAudio.url === streamUrl || currentAudio.url === liveHlsUrl())) return;
  if (pendingHlsStream?.url === streamUrl) return;
  hlsLog('received a server HLS stream announcement', { streamUrl, generation });
  pendingHlsStream = {
    url: streamUrl,
    generation: hlsGeneration,
    transport: 'hls',
    epoch: audioEpoch,
  };
  prepareHlsStream(pendingHlsStream);
  if (audioPrimed) void startPendingHlsStream();
}

async function startPendingHlsStream() {
  if (!audioPrimed) return;
  if (!pendingHlsStream && selectedHlsTransport) {
    // The source URL is stable before a generation exists. Its server request
    // blocks until this tap's Play control creates the actual HLS stream.
    pendingHlsStream = {
      url: liveHlsUrl(),
      generation: hlsGeneration,
      transport: 'hls',
      player: selectedHlsTransport,
      epoch: audioEpoch,
    };
  }
  if (!pendingHlsStream) return;
  const item = pendingHlsStream;
  if (currentAudio?.transport === 'hls' && currentAudio.url === item.url && audioPlaying) return;
  if (!prepareHlsStream(item)) {
    pendingHlsStream = null;
    audioPrimed = false;
    audioStartNeedsGesture = true;
    notify('This browser cannot play the live HLS stream; using WAV clips instead.', true);
    return;
  }
  pendingHlsStream = null;
  if (currentAudio) {
    resetAudioPlayer();
    item.prepared = false;
    if (!prepareHlsStream(item)) return;
  }
  audioPlaying = true;
  currentAudio = item;
  hlsLog('starting HLS stream in the media element', { streamUrl: item.url, generation: item.generation });
  updateMediaSession();
  try {
    audioPlayer.loop = false;
    audioPlayer.volume = 1;
    // The play() invocation happens synchronously while handling the tap.
    // Do not await any network or server operation before this line.
    await audioPlayer.play();
    if (currentAudio === item) updateMediaSession();
  } catch (error) {
    hlsError('HLS media playback failed to start', error, { streamUrl: item.url, generation: item.generation });
    failAudio(item, error);
  }
}

async function acknowledgeAudio(id) {
  try { await remoteRequest('/api/audio-complete', { id }); }
  catch (error) { notify(`Could not confirm audio playback: ${error?.message || 'connection lost.'}`, true); }
}

function failAudio(item, error) {
  if (currentAudio !== item || item?.epoch !== audioEpoch) return;
  if (item?.transport === 'hls') {
    hlsError('HLS playback failed', error, { streamUrl: item.url, generation: item.generation });
  }
  // Do not send Pause to the desktop reader here. The previous failure path
  // did that, turning a mobile decoding or autoplay rejection into an
  // immediate app-wide pause. Keep the finite clip ready for a user retry.
  if (item.transport === 'hls') {
    // resetAudioPlayer() tears down the attached source/player; a retry must
    // attach it again instead of trying to play a destroyed media pipeline.
    item.prepared = false;
    pendingHlsStream = item;
  }
  else audioQueue.unshift({ id: item.id, url: item.url, volume: item.volume });
  audioPrimed = false;
  audioStartNeedsGesture = true;
  resetAudioPlayer();
  updateMediaSession();
  notify(`Audio could not start: ${error?.message || 'tap Play to retry.'}`, true);
}

async function playNextAudio() {
  if (audioPlaying || !audioPrimed || !audioQueue.length) return;
  const item = { ...audioQueue.shift(), epoch: audioEpoch };
  audioPlaying = true;
  currentAudio = item;
  updateMediaSession();
  try {
    audioPlayer.loop = false;
    audioPlayer.src = item.url;
    const volume = Number(item.volume);
    audioPlayer.volume = Number.isFinite(volume) ? Math.max(0, Math.min(1, volume)) : 1;
    audioPlayer.load();
    await audioPlayer.play();
    if (currentAudio === item) updateMediaSession();
  } catch (error) {
    failAudio(item, error);
  }
}

audioPlayer.addEventListener('ended', () => {
  const item = currentAudio;
  if (!item || item.epoch !== audioEpoch) return;
  currentAudio = null;
  audioPlaying = false;
  updateMediaSession();
  if (item.transport === 'hls') return;
  void acknowledgeAudio(item.id);
  void playNextAudio();
});
audioPlayer.addEventListener('error', () => {
  const item = currentAudio?.transport === 'hls' ? currentAudio : pendingHlsStream;
  if (item?.transport === 'hls') {
    hlsError('the media element raised an HLS error', audioPlayer.error, {
      streamUrl: item.url,
      generation: item.generation,
    });
  }
  failAudio(currentAudio, audioPlayer.error);
});
audioPlayer.addEventListener('loadedmetadata', updateMediaSessionPosition);
audioPlayer.addEventListener('timeupdate', updateMediaSessionPosition);

$('#play-pause').addEventListener('click', () => control(
  state.playback_mode && !audioStartNeedsGesture ? 'pause' : 'play'
));
$('#back').addEventListener('click', () => control('back'));
$('#forward').addEventListener('click', () => control('forward'));
$('#stop').addEventListener('click', () => control('stop'));
$('#speed').addEventListener('input', (event) => {
  $('#speed-value').textContent = `${Number(event.target.value).toFixed(2)}x`;
  bridge('set_speed', event.target.value).catch((error) => notify(error.message, true));
});
$('#mode').addEventListener('change', (event) => bridge('set_mode', event.target.value === 'dialog').catch((error) => notify(error.message, true)));
script.addEventListener('input', () => {
  renderHighlights();
  clearTimeout(textTimer);
  textTimer = setTimeout(() => bridge('set_text', script.value).catch((error) => notify(error.message, true)), 150);
});
script.addEventListener('scroll', () => { highlights.scrollTop = script.scrollTop; highlights.scrollLeft = script.scrollLeft; });
script.addEventListener('blur', () => bridge('set_text', script.value).catch(() => { }));

function scheduleHighlightRender() {
  cancelAnimationFrame(highlightRenderFrame);
  highlightRenderFrame = requestAnimationFrame(renderHighlights);
}

if (window.ResizeObserver) {
  new ResizeObserver(scheduleHighlightRender).observe(script);
} else {
  window.addEventListener('resize', scheduleHighlightRender);
}

function syncReaderSettingsLayout() {
  toolbar.classList.remove('compact-settings');
  if (readerSettings.hidden) return;
  toolbar.classList.toggle('compact-settings', toolbar.scrollWidth > toolbar.clientWidth + 1);
}

function setReaderSettings(open) {
  readerSettings.hidden = !open;
  const action = open ? 'Hide' : 'Show';
  readerSettingsToggle.setAttribute('aria-expanded', String(open));
  readerSettingsToggle.setAttribute('aria-label', `${action} reading settings`);
  readerSettingsToggle.title = `${action} reading settings`;
  requestAnimationFrame(syncReaderSettingsLayout);
}

function setMobileView(view) {
  if (!['read', 'controls'].includes(view)) return;
  app.dataset.mobileView = view;
  mobileTabs.forEach((tab) => {
    const selected = tab.dataset.mobileView === view;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
}

function openSearch() {
  if (mobileLayout.matches) setMobileView('read');
  setReaderSettings(true);
  requestAnimationFrame(() => $('#search-query').focus());
}
function closeSearch() {
  $('#search-query').value = '';
  lastActiveRange = '';
  renderHighlights();
  requestAnimationFrame(() => script.focus());
}
function findText() {
  const query = $('#search-query').value;
  if (!query) return;
  const start = script.value.toLocaleLowerCase().indexOf(query.toLocaleLowerCase());
  if (start < 0) { notify('No match found.'); return; }
  script.focus(); script.setSelectionRange(start, start + query.length);
  const before = script.value.slice(0, start); const line = before.split('\n').length;
  state.seek_lines = { start_line: line, end_line: line };
  lastActiveRange = ''; renderHighlights();
}
$('#find').addEventListener('click', findText);
$('#close-search').addEventListener('click', closeSearch);
$('#search-query').addEventListener('keydown', (event) => { if (event.key === 'Enter') findText(); if (event.key === 'Escape') closeSearch(); });
document.addEventListener('keydown', (event) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'f') { event.preventDefault(); openSearch(); } });
document.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && ['+', '=', '-', '0'].includes(event.key)) event.preventDefault();
});
document.addEventListener('wheel', (event) => {
  if (event.ctrlKey || event.metaKey) event.preventDefault();
}, { passive: false });
document.addEventListener('gesturestart', (event) => event.preventDefault(), { passive: false });
document.addEventListener('gesturechange', (event) => event.preventDefault(), { passive: false });
document.addEventListener('touchmove', (event) => {
  if (event.touches.length > 1) event.preventDefault();
}, { passive: false });
script.addEventListener('wheel', (event) => { if (event.ctrlKey || event.metaKey) { event.preventDefault(); bridge('change_font_size', event.deltaY < 0 ? 1 : -1); } }, { passive: false });
document.querySelectorAll('[data-font-size-change]').forEach((button) => {
  button.addEventListener('click', () => bridge('change_font_size', Number(button.dataset.fontSizeChange)));
});
$('#paste').addEventListener('click', async () => {
  try {
    const result = await bridge('read_clipboard');
    if (!result.ok) throw new Error(result.message);
    const text = richClipboardToText(result.html, result.text);
    script.value = text; renderHighlights(); await bridge('set_text', text);
    if (result.source === 'desktop') notify('Pasted from the desktop clipboard.');
  } catch (error) { notify(error.message || 'Clipboard access was unavailable. Use Ctrl+V in the editor instead.', true); script.focus(); }
});
$('#server-toggle').addEventListener('click', async () => {
  try { const result = await bridge('toggle_server', $('#server-port').value); if (!result.ok) notify(result.message || 'Sharing could not be started.', true); }
  catch (error) { notify(error.message, true); }
});

$('#character-list').addEventListener('change', async (event) => {
  const result = await bridge('select_character', event.target.value); if (!result.ok) notify(result.message, true);
});
$('#add-character').addEventListener('click', async () => { const result = await bridge('add_character'); if (!result.ok) notify(result.message, true); });
$('#delete-character').addEventListener('click', async () => {
  const name = $('#character-list').value; if (!name) return;
  const result = await bridge('delete_character', name); if (!result.ok) notify(result.message, true);
});
$('#character-name').addEventListener('change', async (event) => {
  const oldName = state.characters?.selected; if (!oldName) return;
  const result = await bridge('rename_character', oldName, event.target.value); if (!result.ok) notify(result.message, true);
});
async function saveCharacter() {
  const name = state.characters?.selected; if (!name) return;
  const result = await bridge('update_character', name, $('#character-voice').value, $('#character-speed').value, $('#character-volume').value);
  if (!result.ok) notify(result.message, true);
}
$('#character-voice').addEventListener('change', saveCharacter);
$('#character-speed').addEventListener('change', saveCharacter);
$('#character-volume').addEventListener('change', saveCharacter);

readerSettingsToggle.addEventListener('click', () => setReaderSettings(readerSettings.hidden));
mobileTabs.forEach((tab, index) => {
  tab.addEventListener('click', () => setMobileView(tab.dataset.mobileView));
  tab.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const next = mobileTabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + mobileTabs.length) % mobileTabs.length];
    setMobileView(next.dataset.mobileView);
    next.focus();
  });
});
window.addEventListener('resize', syncReaderSettingsLayout);
function syncMobileViewportHeight() {
  if (!mobileLayout.matches) {
    document.documentElement.style.removeProperty('--mobile-viewport-height');
    return;
  }
  const height = window.visualViewport?.height || window.innerHeight;
  document.documentElement.style.setProperty('--mobile-viewport-height', `${Math.round(height)}px`);
}
window.addEventListener('resize', syncMobileViewportHeight);
window.visualViewport?.addEventListener('resize', syncMobileViewportHeight);
window.visualViewport?.addEventListener('scroll', syncMobileViewportHeight);
if (mobileLayout.addEventListener) mobileLayout.addEventListener('change', syncMobileViewportHeight);
else mobileLayout.addListener(syncMobileViewportHeight);
syncMobileViewportHeight();
syncReaderSettingsLayout();

const splitter = $('#splitter');
splitter.addEventListener('pointerdown', (event) => {
  if (window.matchMedia('(max-width: 900px)').matches) return;
  event.preventDefault();
  splitter.setPointerCapture(event.pointerId);
  document.body.classList.add('resizing');
  const resize = (moveEvent) => {
    const width = Math.max(270, Math.min(window.innerWidth * .65, window.innerWidth - moveEvent.clientX));
    document.documentElement.style.setProperty('--sidebar-width', `${width}px`);
  };
  const finish = () => {
    document.body.classList.remove('resizing');
    splitter.removeEventListener('pointermove', resize);
    splitter.removeEventListener('pointerup', finish);
    splitter.removeEventListener('pointercancel', finish);
  };
  splitter.addEventListener('pointermove', resize);
  splitter.addEventListener('pointerup', finish);
  splitter.addEventListener('pointercancel', finish);
});

async function startRemoteSession() {
  try {
    configureMediaSession();
    selectedHlsTransport = getHlsTransport();
    const hlsRequested = selectedHlsTransport !== null;
    hlsLog('probing playback capability', {
      isMobile: isMobileDevice(),
      nativeHls: supportsNativeHls(),
      mseHls: supportsMseHls(),
      selectedHlsTransport,
      hlsRequested,
      canPlayType: {
        standard: audioPlayer.canPlayType('application/vnd.apple.mpegurl'),
        audio: audioPlayer.canPlayType('audio/mpegurl'),
      },
    });
    const capabilities = await bridge('set_audio_capabilities', hlsRequested);
    hlsLog('server selected an audio transport', capabilities);
    if (!capabilities.hls) selectedHlsTransport = null;
    if (hlsRequested && !capabilities.hls && capabilities.message) {
      notify(capabilities.message, true);
    }
    applyState(await bridge('get_state'));
    const events = new EventSource('/api/events');
    events.addEventListener('state', (event) => applyState(JSON.parse(event.data)));
    events.addEventListener('hls-stream', (event) => {
      const { url, generation } = JSON.parse(event.data);
      if (url) queueHlsStream(url, generation);
    });
    events.addEventListener('audio', (event) => {
      audioQueue.push(JSON.parse(event.data));
      void playNextAudio();
    });
    events.addEventListener('audio-stop', (event) => {
      audioEpoch += 1;
      audioQueue = [];
      audioPrimed = false;
      audioStartNeedsGesture = false;
      pendingHlsStream = null;
      resetAudioPlayer();
      setMediaSessionPlaybackState('paused');
    });
    events.onerror = () => notify('Connection lost. Retrying…', true);
  } catch (error) {
    notify(error.message || 'Could not connect to Voice Reader.', true);
  }
}

window.addEventListener('pagehide', () => {
  if (!remoteMode || !audioClientId) return;
  const payload = JSON.stringify({ client_id: audioClientId });
  try {
    navigator.sendBeacon('/api/audio-release', new Blob([payload], { type: 'application/json' }));
  } catch (_) {
    // The server will release ownership when it is restarted if the browser
    // cannot deliver this best-effort unload notification.
  }
});

let bridgeReady = false;
async function initializeBridge() {
  if (bridgeReady || !window.pywebview?.api?.get_state) return false;
  try {
    applyState(await bridge('get_state'));
    bridgeReady = true;
    applyDesktopColorScheme();
    $('#offline').hidden = true;
    return true;
  } catch (error) {
    $('#offline').querySelector('p').textContent = error.message;
    $('#offline').hidden = false;
    return false;
  }
}

if (remoteMode) {
  startRemoteSession();
} else {
  window.addEventListener('pywebviewready', initializeBridge);
  const bridgePoll = setInterval(async () => {
    if (await initializeBridge()) clearInterval(bridgePoll);
  }, 100);
  setTimeout(() => {
    if (!bridgeReady) $('#offline').hidden = false;
  }, 1200);
}
