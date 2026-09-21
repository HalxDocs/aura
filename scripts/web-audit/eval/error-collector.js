// Init script (passed to `open --init-script`): captures errors from before
// page JS until the collector reads window.__auraErrors. Installs fresh on
// every navigation (init scripts run per document).
(function () {
  window.__auraErrors = [];
  var push = function (kind, msg) {
    if (window.__auraErrors.length < 50) {
      window.__auraErrors.push({
        kind: kind,
        msg: String(msg).slice(0, 300),
        t: Math.round(performance.now()),
      });
    }
  };
  // capture=true also catches resource load failures (img/script/css)
  window.addEventListener(
    "error",
    function (e) {
      if (e.target && e.target !== window && (e.target.src || e.target.href)) {
        push("resource", ((e.target.tagName || "?") + " failed: " + (e.target.src || e.target.href)).slice(0, 300));
      } else {
        push("error", (e.message || "") + " @ " + (e.filename || "") + ":" + (e.lineno || ""));
      }
    },
    true
  );
  window.addEventListener("unhandledrejection", function (e) {
    push("promise", (e.reason && (e.reason.message || e.reason)) || "unknown rejection");
  });
  var origError = console.error.bind(console);
  console.error = function () {
    var args = Array.prototype.slice.call(arguments).map(function (x) {
      if (typeof x === "string") return x;
      if (x && x.message) return x.message;
      try { return JSON.stringify(x).slice(0, 120); } catch (_) { return String(x); }
    });
    push("console.error", args.join(" "));
    origError.apply(null, arguments);
  };
})();
