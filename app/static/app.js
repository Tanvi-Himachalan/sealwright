/* Sealwright front-end: plain JavaScript, no build step.
   All user-supplied text is inserted with textContent (never innerHTML) to prevent XSS. */
(function () {
  const $ = (id) => document.getElementById(id);
  const PAGE = 25, RING = 402.1; // ring circumference = 2 * PI * 64
  let step = 1, mode = "paste", csvFile = null;
  let currentJob = null, filter = "", offset = 0, timer = null;

  // ---------- tiny helpers ----------
  function el(tag, props = {}, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") n.className = v; else if (k === "onclick") n.onclick = v; else n.setAttribute(k, v);
    }
    kids.forEach((k) => n.append(k));
    return n;
  }
  function toast(msg) {
    const t = $("toast"); t.textContent = msg; t.classList.add("show");
    clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), 2400);
  }
  function badge(status) {
    const b = el("span", { class: "badge b-" + status }); b.textContent = status.replaceAll("_", " "); return b;
  }
  async function api(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) {
      let msg = res.status + " " + res.statusText;
      try {
        const body = await res.json();
        if (typeof body.detail === "string") msg = body.detail;
        else if (Array.isArray(body.detail))
          msg = body.detail.map((e) => (e.loc || []).filter((x) => x !== "body").join(".") + ": " + e.msg).join("\n");
      } catch (_) {}
      throw new Error(msg);
    }
    return res.json();
  }
  function starPoints(cx, cy, ro, ri, n) {
    const pts = [];
    for (let i = 0; i < n * 2; i++) {
      const r = i % 2 ? ri : ro, a = (Math.PI * i) / n;
      pts.push((cx + r * Math.cos(a)).toFixed(2) + "," + (cy + r * Math.sin(a)).toFixed(2));
    }
    return pts.join(" ");
  }
  $("star").setAttribute("points", starPoints(20, 20, 19, 16.5, 16));

  function showView(name) {
    $("viewCreate").hidden = name !== "create";
    $("viewJob").hidden = name !== "job";
    window.scrollTo({ top: 0 });
  }
  function showFormError(msg) { const b = $("formError"); b.textContent = msg || ""; b.hidden = !msg; }

  // =====================================================  WIZARD
  $("date").value = new Date().toISOString().slice(0, 10);

  function goStep(n) {
    step = n; showFormError("");
    [1, 2, 3].forEach((i) => ($("pane" + i).hidden = i !== n));
    document.querySelectorAll(".step").forEach((s) => {
      const i = Number(s.dataset.step);
      s.classList.toggle("active", i === n); s.classList.toggle("done", i < n);
      s.querySelector("i").textContent = i < n ? "✓" : i;
    });
    $("back").hidden = n === 1;
    $("next").hidden = n === 3;
    $("submit").hidden = n !== 3;
    if (n === 3) buildReview();
  }

  function parseLines() {
    return $("people").value.split("\n").map((l) => l.trim()).filter(Boolean).map((line) => {
      const parts = line.split(/[,\t]/).map((p) => p.trim());
      return { name: parts[0] || "", email: parts[1] || null, remark: parts.slice(2).join(", ") || null };
    });
  }
  function recipientSummary() {
    if (mode === "csv") return csvFile ? "CSV file: " + csvFile.name : "";
    const n = parseLines().length;
    return n ? n + (n === 1 ? " recipient" : " recipients") + " (pasted)" : "";
  }

  function buildReview() {
    const box = $("review"); box.replaceChildren();
    const items = [
      ["Course / event", $("title").value.trim(), "wide"],
      ["Issued by", $("issuer").value.trim()],
      ["Award title", $("award").value.trim() || "Certificate of Completion"],
      ["Issue date", $("date").value || "today"],
      ["Signatory", [$("sigName").value.trim(), $("sigTitle").value.trim()].filter(Boolean).join(", ") || "Authorised Signatory"],
      ["Recipients", recipientSummary(), "wide"],
    ];
    items.forEach(([k, v, cls]) => {
      const s = el("span"); s.textContent = k;
      const b = el("b"); b.textContent = v;
      box.append(el("div", cls ? { class: cls } : {}, s, b));
    });
  }

  $("next").addEventListener("click", () => {
    if (step === 1) {
      if ($("title").value.trim().length < 2) return showFormError("Enter the course / event name (at least 2 characters).");
      if ($("issuer").value.trim().length < 2) return showFormError("Enter the issuing organisation (at least 2 characters).");
    }
    if (step === 2 && !recipientSummary()) {
      return showFormError(mode === "csv" ? "Choose a CSV file first." : "Add at least one recipient.");
    }
    goStep(step + 1);
  });
  $("back").addEventListener("click", () => goStep(step - 1));

  document.querySelectorAll(".tab").forEach((t) =>
    t.addEventListener("click", () => {
      mode = t.dataset.tab;
      document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
      $("tab-paste").hidden = mode !== "paste";
      $("tab-csv").hidden = mode !== "csv";
      showFormError("");
    })
  );

  $("people").addEventListener("input", () => {
    const n = parseLines().length;
    $("count").textContent = n + (n === 1 ? " recipient" : " recipients");
  });
  $("demo").addEventListener("click", () => {
    if (!$("title").value) $("title").value = "Full-Stack Python Bootcamp 2026";
    if (!$("issuer").value) $("issuer").value = "Frontier Academy";
    if (!$("sigName").value) $("sigName").value = "Dr. A. Rao";
    if (!$("sigTitle").value) $("sigTitle").value = "Program Director";
    $("people").value = [
      "Tanvi Sharma, tanvi@example.com, with Distinction",
      "Arjun Mehta, arjun@example.com, Best Project Award",
      "Meera Iyer, meera@example.com",
      "Rohan Das, rohan@example.com, Top 10 Finalist",
      "Priya N, not-an-email",
      "தன்வி சர்மா, tamil@example.com",
      "Arjun Mehta Again, ARJUN@example.com",
      "Karthik Raman",
    ].join("\n");
    $("people").dispatchEvent(new Event("input"));
    toast("Demo loaded. It includes invalid, duplicate and un-renderable rows on purpose.");
  });

  // CSV drop zone
  const drop = $("drop");
  drop.addEventListener("click", () => $("file").click());
  ["dragover", "dragenter"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach((e) => drop.addEventListener(e, (ev) => { ev.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (ev) => setFile(ev.dataTransfer.files[0]));
  $("file").addEventListener("change", (ev) => setFile(ev.target.files[0]));
  function setFile(f) {
    if (!f) return;
    csvFile = f; $("dropTitle").textContent = "📄 " + f.name + " (" + Math.max(1, Math.round(f.size / 1024)) + " KB)";
    showFormError("");
  }

  $("submit").addEventListener("click", async () => {
    showFormError("");
    const meta = {
      title: $("title").value.trim(), issuer: $("issuer").value.trim(),
      award_title: $("award").value.trim() || "Certificate of Completion",
      issue_date: $("date").value || null,
      signatory_name: $("sigName").value.trim() || null, signatory_title: $("sigTitle").value.trim() || null,
    };
    $("submit").disabled = true;
    try {
      let job;
      if (mode === "paste") {
        job = await api("/api/jobs", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...meta, recipients: parseLines() }),
        });
      } else {
        const fd = new FormData();
        fd.append("file", csvFile);
        Object.entries(meta).forEach(([k, v]) => { if (v) fd.append(k, v); });
        job = await api("/api/jobs/upload", { method: "POST", body: fd });
      }
      toast("Batch accepted: " + job.total + " recipients");
      openJob(job.id);
      loadRecent();
    } catch (e) { showFormError(e.message); }
    finally { $("submit").disabled = false; }
  });

  $("newBtn").addEventListener("click", () => {
    currentJob = null; clearTimeout(timer);
    history.replaceState(null, "", location.pathname);
    goStep(1); showView("create"); loadRecent();
  });

  // =====================================================  DASHBOARD
  function openJob(id) {
    currentJob = id; filter = ""; offset = 0;
    history.replaceState(null, "", "#job=" + id);
    document.querySelectorAll("#filters .chip").forEach((c) => c.classList.toggle("active", c.dataset.f === ""));
    showView("job");
    refresh();
  }

  async function refresh() {
    if (!currentJob) return;
    clearTimeout(timer);
    try {
      const job = await api("/api/jobs/" + currentJob);
      renderJob(job);
      const q = new URLSearchParams({ limit: PAGE, offset });
      if (filter) q.set("status", filter);
      renderRows(await api(job.links.certificates + "?" + q));
      if (["queued", "processing"].includes(job.status)) timer = setTimeout(refresh, 900);
      else loadRecent();
    } catch (e) { toast(e.message); }
  }

  function renderJob(j) {
    const busy = ["queued", "processing"].includes(j.status);
    $("jTitle").textContent = j.title;
    $("jMeta").textContent = j.issuer + " · " + j.award_title + " · " + j.issue_date;
    const st = $("jStatus"); st.className = "badge b-" + j.status; st.textContent = j.status.replaceAll("_", " ");
    $("ringFill").style.strokeDashoffset = RING * (1 - j.progress_percent / 100);
    $("jPercent").textContent = Math.round(j.progress_percent) + "%";
    $("jProcessed").textContent = j.processed + " of " + j.total + " processed";
    $("sGen").textContent = j.counts.generated; $("sInv").textContent = j.counts.invalid;
    $("sFail").textContent = j.counts.failed; $("sPend").textContent = j.counts.pending;
    $("zipBtn").disabled = j.counts.generated === 0;
    $("retryBtn").disabled = j.counts.failed === 0 || busy;
    $("zipBtn").onclick = () => (location.href = j.links.download_zip);
    $("retryBtn").onclick = async () => {
      try { await api(j.links.retry_failed, { method: "POST" }); toast("Retrying failed certificates…"); refresh(); }
      catch (e) { toast(e.message); }
    };
    $("copyApi").onclick = () =>
      navigator.clipboard.writeText(location.origin + j.links.status).then(() => toast("API URL copied"));
  }

  function renderRows(page) {
    const body = $("rows"); body.replaceChildren();
    if (!page.items.length) {
      const td = el("td", { colspan: 5, class: "sub", style: "text-align:center;padding:30px" });
      td.textContent = "Nothing here.";
      body.append(el("tr", {}, td));
    }
    page.items.forEach((c) => {
      const who = el("td");
      const nm = el("div"); nm.textContent = c.name || "(blank)"; who.append(nm);
      const sub = [c.email, c.remark].filter(Boolean).join(" · ");
      if (sub) { const s = el("div", { class: "sub" }); s.textContent = sub; who.append(s); }
      if (c.error) { const e = el("div", { class: "err" }); e.textContent = c.error; who.append(e); }

      const codeTd = el("td"); if (c.code) { const k = el("code"); k.textContent = c.code; codeTd.append(k); }
      const act = el("td", { class: "act" });
      if (c.file_url) {
        const p = el("button", { class: "btn small" }); p.textContent = "Preview"; p.onclick = () => openModal(c);
        const d = el("a", { class: "btn small", href: c.file_url + "?download=true" }); d.textContent = "PDF";
        const v = el("button", { class: "btn small" }); v.textContent = "Verify link";
        v.onclick = () => navigator.clipboard.writeText(c.verify_url).then(() => toast("Verification link copied"));
        act.append(p, " ", d, " ", v);
      }
      const num = el("td"); num.textContent = c.row_number;
      const stTd = el("td"); stTd.append(badge(c.status));
      body.append(el("tr", {}, num, who, stTd, codeTd, act));
    });
    const from = page.total ? page.offset + 1 : 0, to = Math.min(page.offset + page.limit, page.total);
    $("pageInfo").textContent = from + "–" + to + " of " + page.total;
    $("prev").disabled = page.offset === 0; $("next2").disabled = to >= page.total;
  }

  $("prev").onclick = () => { offset = Math.max(0, offset - PAGE); refresh(); };
  $("next2").onclick = () => { offset += PAGE; refresh(); };
  document.querySelectorAll("#filters .chip").forEach((chip) =>
    chip.addEventListener("click", () => {
      filter = chip.dataset.f; offset = 0;
      document.querySelectorAll("#filters .chip").forEach((c) => c.classList.toggle("active", c === chip));
      refresh();
    })
  );

  // ---------- preview modal ----------
  function openModal(c) {
    $("mTitle").textContent = c.name + " · " + c.code;
    $("mFrame").src = c.file_url + "#toolbar=0&navpanes=0";
    $("mDownload").href = c.file_url + "?download=true";
    $("modal").classList.add("show");
  }
  const closeModal = () => { $("modal").classList.remove("show"); $("mFrame").src = "about:blank"; };
  $("mClose").onclick = closeModal;
  $("modal").addEventListener("click", (e) => { if (e.target === $("modal")) closeModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

  // ---------- sidebar: recent batches ----------
  async function loadRecent() {
    try {
      const jobs = await api("/api/jobs?limit=15");
      const box = $("recent"); box.replaceChildren();
      if (!jobs.length) { const p = el("p", { class: "hint" }); p.textContent = "No batches yet."; box.append(p); return; }
      jobs.forEach((j) => {
        const t = el("div", { class: "t" }); const b = el("b"); b.textContent = j.title;
        const s = el("span"); s.textContent = j.counts.generated + "/" + j.total + " · " + new Date(j.created_at).toLocaleDateString();
        t.append(b, s);
        const item = el("div", { class: "recent-item" + (j.id === currentJob ? " active" : "") }, t, badge(j.status));
        item.onclick = () => openJob(j.id);
        box.append(item);
      });
    } catch (_) {}
  }

  // ---------- init ----------
  goStep(1);
  loadRecent();
  const m = location.hash.match(/job=([\w-]+)/);
  if (m) openJob(m[1]); else showView("create");
})();
