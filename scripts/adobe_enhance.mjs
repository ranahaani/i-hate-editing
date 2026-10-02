// Adobe Podcast Enhance Speech, driven through the signed-in ego-browser session.
// Run by scripts/enhance.py, which prepends `const JOB = {...}` (input, output, model).
//
// Flow measured from podcast.adobe.com/en/enhance network traffic (2026-10-02):
//   1. POST {API}/rails/active_storage/direct_uploads   {blob: {filename, content_type, byte_size, checksum}}
//   2. PUT  the file to the returned S3 direct_upload url with its headers
//   3. POST {API}/api/v1/enhance_speech_tracks          {id, track_name, model_version, signed_id}
//   4. GET  {API}/api/v1/enhance_speech_tracks/{id}     until finished_processing_at or error_type
//   5. GET  {API}/api/v1/enhance_speech_tracks/{id}/merged_media -> {url}: 8-channel FLAC of stems
// Auth is the page's own IMS token (Authorization: Bearer) plus X-Api-Key = IMS client id.

const fs = await import("node:fs/promises");
const crypto = await import("node:crypto");
const path = await import("node:path");

const API = "https://phonos-server-flex.adobe.io";
const POLL_MS = 5000;
const TIMEOUT_MS = 15 * 60 * 1000;

const task = await taskSpace("adobe enhance " + path.basename(JOB.input));
const page = task.page("p1");
try {
  await page.goto("https://podcast.adobe.com/en/enhance");
  await page.waitForFunction(() => !!window.adobeIMS?.getAccessToken?.()?.token, undefined, { timeout: 30_000 })
    .catch(() => { throw new Error("NOT_SIGNED_IN: sign in to podcast.adobe.com in ego-browser, then rerun"); });
  const auth = await page.evaluate(() => ({ token: window.adobeIMS.getAccessToken().token, key: window.adobeid.client_id }));
  const headers = { Authorization: `Bearer ${auth.token}`, "X-Api-Key": auth.key, "Content-Type": "application/json",
                    Origin: "https://podcast.adobe.com", Referer: "https://podcast.adobe.com/" };
  const api = async (method, url, body) => {
    const res = await fetch(url, { method, headers, body: body && JSON.stringify(body) });
    const text = await res.text();
    if (!res.ok) throw new Error(`${method} ${url.split("?")[0]} -> ${res.status}: ${text.slice(0, 300)}`);
    return text ? JSON.parse(text) : {};
  };

  const file = await fs.readFile(JOB.input);
  const name = path.basename(JOB.input);
  const blob = await api("POST", `${API}/rails/active_storage/direct_uploads`, { blob: {
    filename: name, content_type: "audio/wav", byte_size: file.length,
    checksum: crypto.createHash("md5").update(file).digest("base64") } });
  const up = await fetch(blob.direct_upload.url, { method: "PUT", headers: blob.direct_upload.headers, body: file });
  if (!up.ok) throw new Error(`S3 upload -> ${up.status}`);

  const id = crypto.randomUUID();
  await api("POST", `${API}/api/v1/enhance_speech_tracks?time=${Date.now()}`,
            { id, track_name: name, model_version: JOB.model, signed_id: blob.signed_id });
  const t0 = Date.now();
  let track;
  for (;;) {
    track = await api("GET", `${API}/api/v1/enhance_speech_tracks/${id}?time=${Date.now()}`);
    if (track.error_type) throw new Error(`enhance failed: ${track.error_type} limits=${JSON.stringify(track.limits)}`);
    if (track.finished_processing_at) break;
    if (Date.now() - t0 > TIMEOUT_MS) throw new Error("enhance timed out");
    await new Promise((r) => setTimeout(r, POLL_MS));
  }
  const media = await api("GET", `${API}/api/v1/enhance_speech_tracks/${id}/merged_media`);
  const res = await fetch(media.url);
  if (!res.ok) throw new Error(`merged_media download -> ${res.status}`);
  await fs.writeFile(JOB.output, Buffer.from(await res.arrayBuffer()));
  console.log(JSON.stringify({ ok: true, id, model: track.model_version, seconds: (Date.now() - t0) / 1000,
                               duration: track.duration, output: JOB.output }));
} finally {
  await task.finish({ keep: [] });
}
