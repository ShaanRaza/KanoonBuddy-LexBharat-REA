/* Shared helpers for the sign-in, sign-up, verify and reset pages. */
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var qs = new URLSearchParams(location.search);
  // only same-site paths are ever used as a post-login destination
  var back = qs.get("redirect");
  if (!back || back.charAt(0) !== "/" || back.charAt(1) === "/" || back.indexOf("\\") !== -1) back = "/dashboard";
  var suffix = back === "/dashboard" ? "" : "?redirect=" + encodeURIComponent(back);

  function show(m, kind) { var e = $("msg"); if (!e) return; e.textContent = m || ""; e.className = m ? "msg show " + (kind || "err") : "msg"; }
  async function post(url, body) {
    var r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
    var j = await r.json().catch(function () { return {}; });
    j._status = r.status; j._retry = parseInt(r.headers.get("Retry-After") || "0", 10);
    return j;
  }
  function wait(j) { var s = j._retry; return "Too many attempts. Try again in " + (s > 90 ? Math.ceil(s / 60) + " minutes" : "a minute") + "."; }
  window.LB = { $: $, qs: qs, back: back, suffix: suffix, show: show, post: post, wait: wait };
})();
