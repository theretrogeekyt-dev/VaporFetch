async function requestJson(url, options) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    const message = Array.isArray(detail) ? detail[0]?.msg : detail;
    throw new Error(message || `Request failed (HTTP ${response.status}).`);
  }
  return payload;
}

function setupAppIdForm(onQueued) {
  const form = document.getElementById("appIdForm");
  const input = document.getElementById("manualAppId");
  const submit = form.querySelector("button");
  const status = document.getElementById("appIdStatus");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    status.textContent = "Adding to queue…";
    try {
      const appid = Number(input.value);
      const result = await requestJson("/api/queue", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({games: [{appid}]}),
      });
      status.textContent = result.added_count ? `App ${appid} queued.` : `App ${appid} is already in the queue.`;
      input.value = "";
      onQueued();
    } catch (error) {
      status.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });
}
