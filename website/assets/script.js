/* ---------- terminal typing demo (runs once, on first view) ---------- */
(function () {
  const cmdEl = document.getElementById("typed-cmd");
  const outEl = document.getElementById("typed-output");
  const shot = document.getElementById("transcript");
  if (!cmdEl || !outEl || !shot) return;

  const cmd = "nyx audit example.com";
  const rows = [
    { sev: "info", text: "A record(s) — 93.184.216.34" },
    { sev: "info", text: "DNSSEC — DNSKEY record published" },
    { sev: "info", text: "Negotiated TLS protocol — TLSv1.3" },
    { sev: "medium", text: "Missing security headers — content-security-policy" },
  ];

  function typeChar(i) {
    cmdEl.textContent = cmd.slice(0, i);
    if (i < cmd.length) {
      setTimeout(() => typeChar(i + 1), 40);
    } else {
      setTimeout(showOutput, 400);
    }
  }

  function showOutput() {
    let html = "";
    rows.forEach((r) => {
      html += `<div class="row"><span class="sev ${r.sev}">${r.sev}</span><span>${r.text}</span></div>`;
    });
    html += '<div class="grade-line">Audit summary — grade <span class="grade-pill">A</span> (94/100)</div>';
    outEl.innerHTML = html;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          typeChar(0);
          observer.disconnect();
        }
      });
    },
    { threshold: 0.4 }
  );
  observer.observe(shot);
})();

/* ---------- scroll reveal ---------- */
(function () {
  const els = document.querySelectorAll(".reveal");
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12 }
  );
  els.forEach((el) => observer.observe(el));
})();
