(() => {
  const state = {
    episodeId: null,
    mediaRecorder: null,
    webcamStream: null,
    recordedChunks: [],
  };

  const $ = (id) => document.getElementById(id);
  const statusText = $("status-text");
  const decisionAction = $("decision-action");
  const decisionReason = $("decision-reason");
  const decisionSummary = $("decision-summary");
  const evidenceList = $("evidence-list");
  const qualityScore = $("quality-score");
  const reviewHint = $("review-hint");

  function setStatus(msg) {
    statusText.textContent = msg;
  }

  async function api(path, options = {}) {
    const res = await fetch(path, options);
    const contentType = res.headers.get("content-type") || "";
    let body;
    if (contentType.includes("application/json")) {
      body = await res.json();
    } else {
      body = await res.text();
    }
    if (!res.ok) {
      const detail = body?.detail || body || res.statusText;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return body;
  }

  function renderEpisode(ep) {
    state.episodeId = ep.episode_id;
    const d = ep.decision_payload;
    decisionAction.textContent = d?.action || ep.decision || "—";
    decisionAction.className = "decision " + ((d?.action || ep.decision || "").includes("RETAKE") ? "retake" : "review");
    decisionReason.textContent = d?.reason_code || ep.reason_code || "";
    decisionSummary.textContent = d?.summary || "";
    qualityScore.textContent = d?.quality_score ?? ep.quality_score ?? "—";

    evidenceList.innerHTML = "";
    (d?.checks || []).forEach((c) => {
      const li = document.createElement("li");
      li.className = c.passed ? "pass" : "fail";
      li.textContent = `${c.passed ? "PASS" : "FAIL"} · ${c.name}: ${c.detail}`;
      evidenceList.appendChild(li);
    });

    const original = $("video-original");
    const annotated = $("video-annotated");
    if (ep.media?.["original.mp4"]) {
      original.src = ep.media["original.mp4"] + `?t=${Date.now()}`;
    }
    if (ep.media?.["annotated.mp4"]) {
      annotated.src = ep.media["annotated.mp4"] + `?t=${Date.now()}`;
    }

    const canReview = (d?.action || ep.decision) === "REVIEW_REQUIRED" && ep.review_status === "PENDING";
    $("btn-approve").disabled = !canReview;
    $("btn-reject").disabled = !canReview;
    $("btn-download").disabled = ep.status !== "processed";
    if (canReview) {
      reviewHint.textContent = "Evidence supports review. Approve or reject this episode.";
    } else if ((d?.action || ep.decision) === "RETAKE_REQUIRED") {
      reviewHint.textContent = "Retake required — approval is blocked by design.";
    } else if (ep.review_status === "APPROVED" || ep.review_status === "REJECTED") {
      reviewHint.textContent = `Review complete: ${ep.review_status}`;
    } else {
      reviewHint.textContent = "Process an episode with REVIEW_REQUIRED to enable controls.";
    }

    drawTrajectory(ep.episode_id);
    refreshLedger();
  }

  async function drawTrajectory(episodeId) {
    const canvas = $("traj-canvas");
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#334456";
    ctx.strokeRect(8, 8, canvas.width - 16, canvas.height - 16);
    // zone guides
    ctx.fillStyle = "rgba(43,183,160,0.15)";
    ctx.fillRect(8, 8, (canvas.width - 16) * 0.22, canvas.height - 16);
    ctx.fillStyle = "rgba(240,162,2,0.15)";
    ctx.fillRect(8 + (canvas.width - 16) * 0.76, 8, (canvas.width - 16) * 0.22, canvas.height - 16);

    try {
      const data = await api(`/api/episodes/${episodeId}/trajectory`);
      const pts = data.points || [];
      if (!pts.length) return;
      ctx.beginPath();
      pts.forEach((p, i) => {
        const x = 8 + p.nx * (canvas.width - 16);
        const y = 8 + p.ny * (canvas.height - 16);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.strokeStyle = "#2bb7a0";
      ctx.lineWidth = 2;
      ctx.stroke();
      const last = pts[pts.length - 1];
      ctx.fillStyle = "#f0a202";
      ctx.beginPath();
      ctx.arc(8 + last.nx * (canvas.width - 16), 8 + last.ny * (canvas.height - 16), 4, 0, Math.PI * 2);
      ctx.fill();
    } catch (err) {
      console.warn(err);
    }
  }

  async function runScenario(name) {
    try {
      setStatus(`Generating & processing ${name}…`);
      const ep = await api(`/api/scenarios/${name}`, { method: "POST" });
      renderEpisode(ep);
      setStatus(`Scenario '${name}' complete · ${ep.decision}`);
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
  }

  async function uploadAndProcess() {
    const input = $("file-input");
    if (!input.files?.length) {
      setStatus("Choose a video file first.");
      return;
    }
    try {
      setStatus("Uploading…");
      const fd = new FormData();
      fd.append("file", input.files[0]);
      const up = await api("/api/episodes/upload", { method: "POST", body: fd });
      setStatus("Processing upload…");
      const ep = await api(`/api/episodes/${up.episode_id}/process`, { method: "POST" });
      renderEpisode(ep);
      setStatus(`Upload processed · ${ep.decision}`);
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
  }

  async function review(action) {
    if (!state.episodeId) return;
    try {
      const ep = await api(`/api/episodes/${state.episodeId}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, reviewer: "dashboard-user", notes: "" }),
      });
      renderEpisode(ep);
      setStatus(`Review ${action}d`);
    } catch (err) {
      setStatus(`Review blocked: ${err.message}`);
    }
  }

  function downloadZip() {
    if (!state.episodeId) return;
    window.location.href = `/api/episodes/${state.episodeId}/download`;
  }

  async function refreshLedger() {
    const tbody = $("ledger-table").querySelector("tbody");
    tbody.innerHTML = "";
    try {
      const rows = await api("/api/episodes");
      rows.forEach((r) => {
        const tr = document.createElement("tr");
        tr.className = "clickable";
        tr.innerHTML = `
          <td>${r.episode_id}</td>
          <td>${r.created_at}</td>
          <td>${r.scenario || "upload"}</td>
          <td>${r.decision || "—"}</td>
          <td>${r.review_status}</td>
          <td>${r.quality_score ?? "—"}</td>
          <td>${r.tracked_frames}/${r.total_frames}</td>
          <td><a href="/api/episodes/${r.episode_id}/download">ZIP</a></td>`;
        tr.addEventListener("click", async (e) => {
          if (e.target.tagName === "A") return;
          const detail = await api(`/api/episodes/${r.episode_id}`);
          $("ledger-detail").classList.remove("hidden");
          $("ledger-detail-body").textContent = JSON.stringify(detail, null, 2);
          renderEpisode(detail);
          document.querySelector('[data-panel="studio"]').click();
        });
        tbody.appendChild(tr);
      });
    } catch (err) {
      setStatus(`Ledger error: ${err.message}`);
    }
  }

  async function startWebcam() {
    try {
      state.webcamStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
      $("webcam").srcObject = state.webcamStream;
      $("btn-webcam-record").disabled = false;
      $("btn-webcam-stop").disabled = false;
      setStatus("Webcam started");
    } catch (err) {
      setStatus(`Webcam unavailable: ${err.message}`);
    }
  }

  function stopWebcam() {
    if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
      state.mediaRecorder.stop();
    }
    state.webcamStream?.getTracks().forEach((t) => t.stop());
    $("webcam").srcObject = null;
    $("btn-webcam-record").disabled = true;
    $("btn-webcam-stop").disabled = true;
    setStatus("Webcam stopped");
  }

  async function recordWebcam() {
    if (!state.webcamStream) return;
    state.recordedChunks = [];
    const mime = MediaRecorder.isTypeSupported("video/webm;codecs=vp9")
      ? "video/webm;codecs=vp9"
      : "video/webm";
    state.mediaRecorder = new MediaRecorder(state.webcamStream, { mimeType: mime });
    state.mediaRecorder.ondataavailable = (e) => {
      if (e.data.size) state.recordedChunks.push(e.data);
    };
    state.mediaRecorder.onstop = async () => {
      try {
        const blob = new Blob(state.recordedChunks, { type: "video/webm" });
        const file = new File([blob], "webcam.webm", { type: "video/webm" });
        // Convert path: upload accepts mp4/avi/mov/mkv — remux note for user if rejected.
        // Try upload as .mkv alias won't work; convert via server not available.
        // For webcam we upload as .mp4 content-type trick won't help OpenCV.
        // Use FormData with .webm and extend server OR tell user.
        // We'll attempt upload with .avi extension won't decode.
        // Better: extend upload to accept webm. Done in a quick fix if needed.
        const fd = new FormData();
        fd.append("file", file, "webcam.webm");
        setStatus("Uploading webcam clip…");
        const up = await api("/api/episodes/upload", { method: "POST", body: fd });
        const ep = await api(`/api/episodes/${up.episode_id}/process`, { method: "POST" });
        renderEpisode(ep);
        setStatus(`Webcam clip processed · ${ep.decision}`);
      } catch (err) {
        setStatus(`Webcam process error: ${err.message}`);
      }
    };
    state.mediaRecorder.start();
    setStatus("Recording 4 seconds…");
    setTimeout(() => {
      if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
        state.mediaRecorder.stop();
      }
    }, 4000);
  }

  // Tabs
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $(`panel-${btn.dataset.panel}`).classList.add("active");
      if (btn.dataset.panel === "ledger") refreshLedger();
    });
  });

  $("btn-successful").addEventListener("click", () => runScenario("successful"));
  $("btn-incomplete").addEventListener("click", () => runScenario("incomplete"));
  $("btn-occluded").addEventListener("click", () => runScenario("occluded"));
  $("btn-upload").addEventListener("click", uploadAndProcess);
  $("btn-approve").addEventListener("click", () => review("approve"));
  $("btn-reject").addEventListener("click", () => review("reject"));
  $("btn-download").addEventListener("click", downloadZip);
  $("btn-refresh-ledger").addEventListener("click", refreshLedger);
  $("btn-webcam-start").addEventListener("click", startWebcam);
  $("btn-webcam-stop").addEventListener("click", stopWebcam);
  $("btn-webcam-record").addEventListener("click", recordWebcam);

  // Boot
  api("/api/health").then((h) => {
    $("opencv-badge").textContent = `OpenCV ${h.opencv}`;
    setStatus(`Ready · ${h.app} v${h.version}`);
  }).catch((err) => setStatus(`Health check failed: ${err.message}`));

  api("/api/config").then((c) => {
    $("formula-box").textContent =
      "Quality score formula (transparent heuristic):\n" + c.quality_formula +
      "\n\nAWS S3 enabled: " + c.aws_s3_enabled + "\n" + c.aws_note;
  });
})();
