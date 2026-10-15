/* LexBharat: "Templates" button in the editor. Pick a standard Indian document, fill in the form, insert it into the open document. */
(function () {
  "use strict";
  var list = null, current = null, modal = null;

  function token() { try { return JSON.parse(localStorage.getItem("lawcentral_auth")).token; } catch (e) { return ""; } }
  function api(path, opts) {
    opts = opts || {}; opts.headers = Object.assign({ Authorization: "Bearer " + token(), "Content-Type": "application/json" }, opts.headers || {});
    return fetch(path, opts).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }
  function el(tag, attrs, kids) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") e.textContent = attrs[k]; else if (k === "class") e.className = attrs[k]; else if (k.slice(0, 2) === "on") e[k] = attrs[k]; else e.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) { if (c) e.appendChild(c); });
    return e;
  }

  var css = document.createElement("style");
  css.textContent =
    "#lbt-ov{position:fixed;inset:0;z-index:80;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;padding:16px;font:14px/1.45 system-ui,sans-serif}" +
    "#lbt{background:#fff;color:#1c1917;border-radius:16px;width:min(980px,100%);height:min(680px,100%);display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.35)}" +
    "#lbt header{display:flex;justify-content:space-between;align-items:center;padding:14px 18px;border-bottom:1px solid #e7e5e4}" +
    "#lbt header h2{margin:0;font-size:18px} #lbt header button{background:none;border:0;font-size:24px;line-height:1;cursor:pointer;color:#6b6761}" +
    "#lbt .bd{display:flex;flex:1;min-height:0} #lbt .side{width:260px;border-right:1px solid #e7e5e4;overflow:auto;padding:10px;flex:none}" +
    "#lbt .side h3{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:#6b6761;margin:12px 6px 4px}" +
    "#lbt .side button{display:block;width:100%;text-align:left;background:none;border:0;border-radius:8px;padding:8px 10px;cursor:pointer;font:inherit;color:inherit}" +
    "#lbt .side button:hover{background:#f5f5f4} #lbt .side button.on{background:#fff1e6;font-weight:700;color:#a84a15}" +
    "#lbt .main{flex:1;overflow:auto;padding:18px 22px} #lbt .main h3{margin:0 0 4px;font-size:18px} #lbt .main p.d{margin:0 0 14px;color:#57534e}" +
    "#lbt label{display:block;font-weight:600;margin:12px 0 4px;font-size:13px} #lbt label .req{color:#b42318}" +
    "#lbt input,#lbt textarea,#lbt select{width:100%;padding:9px 10px;border:1px solid #d6d3d1;border-radius:8px;font:inherit;background:#fff;color:#1c1917}" +
    "#lbt textarea{min-height:70px;resize:vertical} #lbt input:focus,#lbt textarea:focus,#lbt select:focus{outline:2px solid #c2571a;outline-offset:1px}" +
    "#lbt .notes{background:#fffbeb;border:1px solid #fde68a;border-radius:10px;padding:10px 14px;margin:14px 0;font-size:13px} #lbt .notes ul{margin:4px 0 0;padding-left:18px}" +
    "#lbt footer{display:flex;gap:10px;align-items:center;padding:12px 18px;border-top:1px solid #e7e5e4;background:#fafaf9}" +
    "#lbt footer .msg{flex:1;color:#57534e;font-size:13px} #lbt footer button{border-radius:9px;padding:10px 16px;font:700 14px system-ui;cursor:pointer;border:1px solid #c2571a}" +
    "#lbt footer .p{background:#c2571a;color:#fff} #lbt footer .s{background:#fff;color:#c2571a} #lbt footer button[disabled]{opacity:.5;cursor:progress}" +
    "@media (max-width:760px){#lbt .bd{flex-direction:column}#lbt .side{width:auto;border-right:0;border-bottom:1px solid #e7e5e4;max-height:34%}}";
  document.head.appendChild(css);

  function values() {
    var v = {};
    modal.querySelectorAll("[data-key]").forEach(function (i) { v[i.getAttribute("data-key")] = i.value; });
    return v;
  }
  function renderRemote() {
    return api("/api/templates/" + encodeURIComponent(current.id) + "/render", { method: "POST", body: JSON.stringify({ values: values() }) });
  }
  function setMsg(t) { var m = modal.querySelector(".msg"); if (m) m.textContent = t; }

  function doInsert(btn) {
    btn.disabled = true;
    renderRemote().then(function (r) {
      var ed = document.querySelector(".ProseMirror");
      if (!ed) { setMsg("Open the editor first."); return; }
      close();
      ed.focus();
      document.execCommand("insertHTML", false, r.html);
    }).catch(function () { setMsg("Could not build the document. Try again."); }).then(function () { btn.disabled = false; });
  }
  function doCopy(btn) {
    btn.disabled = true;
    renderRemote().then(function (r) {
      var done = function () { setMsg("Copied to clipboard."); };
      if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(r.text).then(done);
      var t = document.createElement("textarea"); t.value = r.text; document.body.appendChild(t); t.select(); document.execCommand("copy"); t.remove(); done();
    }).catch(function () { setMsg("Could not copy."); }).then(function () { btn.disabled = false; });
  }

  function showForm(t) {
    current = t;
    modal.querySelectorAll(".side button").forEach(function (b) { b.classList.toggle("on", b.getAttribute("data-id") === t.id); });
    var main = modal.querySelector(".main"); main.textContent = "";
    main.appendChild(el("h3", { text: t.title })); main.appendChild(el("p", { class: "d", text: t.description }));
    t.fields.forEach(function (f, i) {
      var id = "lbt-f-" + f.key;
      var lab = el("label", { for: id }, [document.createTextNode(f.label + " "), f.required ? el("span", { class: "req", text: "*", "aria-hidden": "true" }) : null]);
      var inp;
      if (f.kind === "textarea") inp = el("textarea", { id: id, "data-key": f.key });
      else if (f.kind === "choice") { inp = el("select", { id: id, "data-key": f.key }, [el("option", { value: "", text: "Select…" })].concat((f.choices || []).map(function (c) { return el("option", { value: c, text: c }); }))); }
      else { inp = el("input", { id: id, "data-key": f.key, type: f.kind === "number" ? "number" : "text", autocomplete: "off" }); }
      if (f.hint) inp.setAttribute("placeholder", f.hint);
      main.appendChild(lab); main.appendChild(inp);
      if (i === 0) setTimeout(function () { inp.focus(); }, 30);
    });
    var notes = el("div", { class: "notes" }, [el("strong", { text: "Before you use it" }), el("ul", {}, (t.notes || []).concat([t.disclaimer]).map(function (n) { return el("li", { text: n }); }))]);
    main.appendChild(notes);
    setMsg("Fields marked * are needed. Blank fields stay as [BRACKETS] in the document.");
  }

  function close() { if (modal) { document.removeEventListener("keydown", onKey, true); modal.remove(); modal = null; } }
  function onKey(e) { if (e.key === "Escape") { e.stopPropagation(); close(); } }

  function open() {
    if (modal) return;
    modal = el("div", { id: "lbt-ov", role: "dialog", "aria-modal": "true", "aria-label": "Templates", onclick: function (e) { if (e.target === modal) close(); } });
    var box = el("div", { id: "lbt" });
    box.appendChild(el("header", {}, [el("h2", { text: "Document templates" }), el("button", { type: "button", "aria-label": "Close", text: "×", onclick: close })]));
    var bd = el("div", { class: "bd" }); var side = el("div", { class: "side" }); var main = el("div", { class: "main" });
    main.appendChild(el("p", { class: "d", text: "Loading templates…" }));
    bd.appendChild(side); bd.appendChild(main); box.appendChild(bd);
    var ins = el("button", { type: "button", class: "p", text: "Insert into document", onclick: function () { doInsert(ins); } });
    var cp = el("button", { type: "button", class: "s", text: "Copy text", onclick: function () { doCopy(cp); } });
    box.appendChild(el("footer", {}, [el("span", { class: "msg", text: "" }), cp, ins]));
    modal.appendChild(box); document.body.appendChild(modal);
    document.addEventListener("keydown", onKey, true);
    var load = list ? Promise.resolve(list) : api("/api/templates").then(function (r) { list = r.templates; return list; });
    load.then(function (ts) {
      var cat = null;
      ts.forEach(function (t) {
        if (t.category !== cat) { cat = t.category; side.appendChild(el("h3", { text: cat })); }
        side.appendChild(el("button", { type: "button", "data-id": t.id, text: t.title.replace(/^[^:]+:\s*/, ""), onclick: function () { showForm(t); } }));
      });
      showForm(ts[0]);
    }).catch(function () { main.textContent = "Could not load templates. Check your connection and try again."; });
  }


  var css2 = document.createElement("style");
  css2.textContent =
    "#lbc-ov{position:fixed;inset:0;z-index:80;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;padding:16px;font:14px/1.5 system-ui,sans-serif}" +
    "#lbc{background:#fff;color:#1c1917;border-radius:16px;width:min(640px,100%);max-height:min(720px,100%);display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.35)}" +
    "#lbc header{display:flex;justify-content:space-between;align-items:center;padding:14px 18px;border-bottom:1px solid #e7e5e4} #lbc header h2{margin:0;font-size:18px}" +
    "#lbc header button{background:none;border:0;font-size:24px;line-height:1;cursor:pointer;color:#6b6761} #lbc .cbody{padding:14px 20px;overflow:auto;flex:1}" +
    "#lbc .sum{font-weight:700;font-size:16px;margin:0 0 6px} #lbc h3{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#6b6761;margin:16px 0 4px}" +
    "#lbc ul{list-style:none;margin:0;padding:0} #lbc li{display:flex;gap:10px;padding:6px 0;border-top:1px solid #f0efed} #lbc li .ic{flex:none;width:20px;text-align:center;font-weight:700}" +
    "#lbc ul.warn .ic{color:#b45309} #lbc ul.ok .ic{color:#067647} #lbc ul.info .ic{color:#6b6761} #lbc a{color:#a84a15} #lbc .mut{color:#6b6761;font-size:13px}" +
    "#lbc footer{display:flex;gap:10px;align-items:center;padding:12px 18px;border-top:1px solid #e7e5e4;background:#fafaf9} #lbc footer .msg{flex:1;color:#57534e;font-size:12.5px}" +
    "#lbc footer button{border-radius:9px;padding:9px 16px;font:700 14px system-ui;cursor:pointer;border:1px solid #c2571a;background:#c2571a;color:#fff}";
  document.head.appendChild(css2);

  /* ---------------------------------------------------------------- Check document */
  var ACTS = [[/bharatiya nagarik suraksha sanhita|\bbnss\b/i, "BNSS"], [/bharatiya nyaya sanhita|\bbns\b/i, "BNS"], [/bharatiya sakshya adhiniyam|\bbsa\b/i, "BSA"],
              [/indian penal code|\bipc\b/i, "IPC"], [/indian evidence act|\biea\b/i, "IEA"], [/negotiable instruments act|n\.?\s?i\.?\s?act|\bnia\b/i, "NIA"]];
  var CRPC_TO_BNSS = { "41": "35", "125": "144", "154": "173", "156": "175", "161": "180", "164": "183", "173": "193", "207": "230", "313": "351", "320": "359", "437": "480", "438": "482", "439": "483", "482": "528" };
  var ACTNAME = "(BNSS|BNS|BSA|IPC|IEA|NIA|NI\\s*Act|N\\.I\\.\\s*Act|Bharatiya Nyaya Sanhita|Bharatiya Nagarik Suraksha Sanhita|Bharatiya Sakshya Adhiniyam|Indian Penal Code|Indian Evidence Act|Negotiable Instruments Act)";
  function actCode(name) { for (var i = 0; i < ACTS.length; i++) if (ACTS[i][0].test(name)) return ACTS[i][1]; return null; }

  function extractRefs(text) {
    var seen = {}, out = [], m;
    var a = new RegExp("\\b(?:section|sec\\.?|s\\.)\\s*(\\d{1,3}[A-Z]?)(?:\\s*\\([\\w]+\\))*\\s*(?:of\\s+(?:the\\s+)?)?" + ACTNAME + "\\b", "gi");
    while ((m = a.exec(text))) { var c = actCode(m[2]); if (c) add(c, m[1].toUpperCase()); }
    var b = new RegExp("\\b(BNSS|BNS|BSA|IPC|IEA|NIA)\\s*(?:section|sec\\.?|s\\.|\\u00a7)?\\s*(\\d{1,3}[A-Z]?)\\b", "g");
    while ((m = b.exec(text))) add(m[1], m[2].toUpperCase());
    function add(code, num) { var k = code + " " + num; if (!seen[k]) { seen[k] = 1; out.push([code, num]); } }
    return out;
  }
  function extractCrpc(text) {
    var out = {}, m, r = /\b(?:section|sec\.?|s\.)\s*(\d{1,3}[A-Z]?)\s*(?:of\s+(?:the\s+)?)?(?:Cr\.?\s?P\.?\s?C\.?|Code of Criminal Procedure)/gi;
    while ((m = r.exec(text))) out[m[1].toUpperCase()] = 1;
    var r2 = /\bCr\.?\s?P\.?\s?C\.?\s*(?:section|sec\.?|s\.)?\s*(\d{1,3}[A-Z]?)/gi;
    while ((m = r2.exec(text))) out[m[1].toUpperCase()] = 1;
    return Object.keys(out);
  }
  function extractCites(text) {
    var res = [], seen = {}, pats = [/\[\d{4}\]\s*(?:Supp\.?\s*)?\d*\s*S\.?\s?C\.?\s?R\.?\s*\d+/gi, /\bAIR\s*(?:\(\d{4}\)\s*|\d{4}\s*)SC\s*\d+/gi, /\(\d{4}\)\s*\d+\s*SCC\s*\d+/gi];
    pats.forEach(function (rx) { var m; while ((m = rx.exec(text))) { var k = m[0].replace(/\s+/g, " ").trim(); if (!seen[k]) { seen[k] = 1; res.push(k); } } });
    return res;
  }

  function openCheck() {
    var ed = document.querySelector(".ProseMirror");
    if (!ed) return;
    var text = ed.innerText || "";
    var ov = el("div", { id: "lbc-ov", role: "dialog", "aria-modal": "true", "aria-label": "Check document" });
    var box = el("div", { id: "lbc" });
    var close = function () { document.removeEventListener("keydown", esc, true); ov.remove(); };
    var esc = function (e) { if (e.key === "Escape") { e.stopPropagation(); close(); } };
    document.addEventListener("keydown", esc, true);
    ov.onclick = function (e) { if (e.target === ov) close(); };
    box.appendChild(el("header", {}, [el("h2", { text: "Check document" }), el("button", { type: "button", "aria-label": "Close", text: "×", onclick: close })]));
    var body = el("div", { class: "cbody" }, [el("p", { class: "mut", text: "Checking…" })]);
    box.appendChild(body);
    box.appendChild(el("footer", {}, [el("span", { class: "msg", text: "This finds blanks and checks references against the library. It does not judge whether your legal argument is right." }),
      el("button", { type: "button", class: "p", text: "Close", onclick: close })]));
    ov.appendChild(box); document.body.appendChild(ov);

    var groups = { warn: [], ok: [], info: [] };
    function add(level, msg, href) { groups[level].push({ msg: msg, href: href }); }
    var words = (text.match(/\S+/g) || []).length;
    if (words === 0) { body.textContent = ""; body.appendChild(el("p", { text: "The document is empty. Write something, or start from a template, then check it." })); return; }

    var ph = text.match(/\[[A-Z][A-Z0-9 ,'’\/()&.\-]{2,70}\]/g) || [], cnt = {};
    ph.forEach(function (p) { cnt[p] = (cnt[p] || 0) + 1; });
    Object.keys(cnt).forEach(function (p) { add("warn", "Not filled in: " + p + (cnt[p] > 1 ? " (" + cnt[p] + " times)" : "")); });
    var blanks = (text.match(/_{4,}/g) || []).length;
    if (blanks) add("info", blanks + " blank line" + (blanks === 1 ? "" : "s") + " (____), usually for signatures, dates or witnesses. Fill them in by hand.");
    if (/affidavit/i.test(text) && !/verif/i.test(text)) add("warn", "This looks like an affidavit but has no Verification clause.");
    if (/affidavit|notice|agreement/i.test(text) && !/\b(19|20)\d{2}\b/.test(text)) add("warn", "No date or year found in the document.");

    var refs = extractRefs(text).slice(0, 25), cites = extractCites(text).slice(0, 15), crpc = extractCrpc(text);
    crpc.forEach(function (n) {
      add("warn", "Cr.P.C. section " + n + ": the Code of Criminal Procedure was repealed from 1 July 2024. " + (CRPC_TO_BNSS[n] ? "The matching provision is BNSS section " + CRPC_TO_BNSS[n] + "." : "Check the matching BNSS section."),
          CRPC_TO_BNSS[n] ? "/statutes/BNSS/" + CRPC_TO_BNSS[n] : null);
    });
    if (/\b(?:C\.?P\.?C\.?|Code of Civil Procedure)\b/.test(text)) add("info", "The Code of Civil Procedure is not in the library, so references to it cannot be checked.");

    var jobs = refs.map(function (r) {
      return fetch("/api/statutes/" + r[0] + "/" + encodeURIComponent(r[1])).then(function (x) {
        if (x.status === 404) { add("warn", r[0] + " section " + r[1] + ": no such section in the library. Check the number.", null); return; }
        return x.json().then(function (j) {
          var s = j.section, link = "/statutes/" + r[0] + "/" + encodeURIComponent(r[1]);
          if (s.status === "repealed") {
            var eq = j.equivalent;
            add("warn", r[0] + " " + r[1] + " (" + s.title + ") is repealed and no longer in force." + (eq ? " The matching provision is " + eq.actCode + " " + eq.number + " (" + eq.title + ")." : " Check the matching section in the new code."), eq ? "/statutes/" + eq.actCode + "/" + encodeURIComponent(eq.number) : link);
          } else add("ok", r[0] + " " + r[1] + ": " + s.title, link);
        });
      }).catch(function () { add("info", r[0] + " " + r[1] + ": could not be checked just now."); });
    }).concat(cites.map(function (c) {
      return api("/api/statutes/cases?q=" + encodeURIComponent(c)).then(function (j) {
        var hit = (j.cases || [])[0];
        if (hit) add("ok", "Case " + c + ": " + hit.title, "/case/" + encodeURIComponent(hit.docId));
        else add("warn", "Case " + c + ": not found in the library. It may still be right, so check it against the report.");
      }).catch(function () { add("info", "Case " + c + ": could not be checked just now."); });
    }));
    Promise.all(jobs).then(function () {
      body.textContent = "";
      var n = groups.warn.length;
      body.appendChild(el("p", { class: "sum", text: n ? n + " thing" + (n === 1 ? "" : "s") + " to look at" : "No problems found. " + (refs.length + cites.length) + " reference" + ((refs.length + cites.length) === 1 ? "" : "s") + " checked." }));
      [["warn", "To look at", "⚠"], ["ok", "Checked and found", "✓"], ["info", "Notes", "i"]].forEach(function (g) {
        if (!groups[g[0]].length) return;
        body.appendChild(el("h3", { text: g[1] }));
        var ul = el("ul", { class: g[0] });
        groups[g[0]].forEach(function (it) {
          var li = el("li", {}, [el("span", { class: "ic", text: g[2], "aria-hidden": "true" })]);
          if (it.href) li.appendChild(el("a", { href: it.href, target: "_blank", rel: "noopener", text: it.msg })); else li.appendChild(document.createTextNode(it.msg));
          ul.appendChild(li);
        });
        body.appendChild(ul);
      });
      body.appendChild(el("p", { class: "mut", text: words + " words checked." + (refs.length >= 25 ? " Only the first 25 section references were checked." : "") }));
    });
  }

  function fab() {
    // On phones the editor header hides its buttons in a menu, so the header buttons have no room: offer floating ones.
    var inEditor = location.pathname.indexOf("/editor") === 0;
    var hb = document.getElementById("lbt-btn"), headerVisible = hb && hb.getBoundingClientRect().width > 0;
    var show = inEditor && !headerVisible && !!document.querySelector(".ProseMirror");
    [["lbt-fab", "Templates", 92, open], ["lbc-fab", "Check", 140, openCheck]].forEach(function (d) {
      var f = document.getElementById(d[0]);
      if (!show) { if (f) f.remove(); return; }
      if (f) return;
      f = document.createElement("button"); f.id = d[0]; f.type = "button"; f.textContent = d[1];
      f.setAttribute("aria-label", d[1] === "Check" ? "Check document" : "Open document templates");
      f.style.cssText = "position:fixed;right:12px;bottom:" + d[2] + "px;z-index:70;background:#c2571a;color:#fff;border:0;border-radius:999px;padding:11px 16px;font:700 14px system-ui,sans-serif;box-shadow:0 6px 20px rgba(0,0,0,.28);cursor:pointer";
      f.onclick = d[3]; document.body.appendChild(f);
    });
  }

  function addButton() {
    fab();
    if (location.pathname.indexOf("/editor") !== 0 || document.getElementById("lbt-btn")) return;
    var imp = [...document.querySelectorAll("button")].find(function (b) { return (b.textContent || "").trim() === "Import" && b.getBoundingClientRect().top < 140; });
    if (!imp) return;
    var b = imp.cloneNode(false);
    b.id = "lbt-btn"; b.type = "button"; b.removeAttribute("title"); b.className = imp.className + " lb-ed-btn";
    b.title = "Start from a standard Indian affidavit, notice or agreement and fill in its details.";
    b.textContent = "Templates"; b.onclick = open; b.style.color = "#a84a15";
    imp.parentNode.insertBefore(b, imp);
    var c = imp.cloneNode(false);
    c.id = "lbc-btn"; c.type = "button"; c.removeAttribute("title"); c.className = imp.className + " lb-ed-btn";
    c.title = "Find blanks you have not filled in, and check the sections and cases you cite against the library.";
    c.textContent = "Check"; c.onclick = openCheck; c.style.color = "#a84a15";
    imp.parentNode.insertBefore(c, imp);
  }
  new MutationObserver(function () { clearTimeout(addButton.t); addButton.t = setTimeout(addButton, 200); }).observe(document.documentElement, { childList: true, subtree: true });
  addButton();
})();
