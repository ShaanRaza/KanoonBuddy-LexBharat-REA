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

  function addButton() {
    if (location.pathname.indexOf("/editor") !== 0 || document.getElementById("lbt-btn")) return;
    var imp = [...document.querySelectorAll("button")].find(function (b) { return (b.textContent || "").trim() === "Import" && b.getBoundingClientRect().top < 140; });
    if (!imp) return;
    var b = imp.cloneNode(false);
    b.id = "lbt-btn"; b.type = "button"; b.removeAttribute("title"); b.className = imp.className + " lb-ed-btn";
    b.title = "Start from a standard Indian affidavit, notice or agreement and fill in its details.";
    b.textContent = "Templates"; b.onclick = open; b.style.color = "#a84a15";
    imp.parentNode.insertBefore(b, imp);
  }
  new MutationObserver(function () { clearTimeout(addButton.t); addButton.t = setTimeout(addButton, 200); }).observe(document.documentElement, { childList: true, subtree: true });
  addButton();
})();
