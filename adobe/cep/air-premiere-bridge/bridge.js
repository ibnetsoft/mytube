(function () {
  "use strict";
  const fs = require("fs");
  const path = require("path");
  const base = path.join(process.env.LOCALAPPDATA, "AirStudio", "premiere_bridge");
  const queue = path.join(base, "queue");
  const status = document.getElementById("status");
  fs.mkdirSync(queue, { recursive: true });
  let busy = false;

  function note(message) {
    status.textContent = message;
  }

  function writeStatus(file, message) {
    fs.writeFileSync(file, message, "utf8");
  }

  function poll() {
    if (busy) return;
    const candidates = fs.readdirSync(queue).filter(name => name.endsWith(".json")).sort();
    if (!candidates.length) {
      note("Waiting for approved project export jobs.");
      return;
    }
    const source = path.join(queue, candidates[0]);
    const claimed = source + ".processing";
    try {
      fs.renameSync(source, claimed);
    } catch (_) {
      return;
    }
    busy = true;
    let job;
    try {
      job = JSON.parse(fs.readFileSync(claimed, "utf8"));
      if (!path.isAbsolute(job.script_path) || !path.isAbsolute(job.status_path)) {
        throw new Error("Bridge job paths must be absolute");
      }
      note("Exporting " + job.project_id + " in Premiere/AME…");
      const jsxPath = job.script_path.replace(/\\/g, "/");
      const command = "$.evalFile(new File(" + JSON.stringify(jsxPath) + "))";
      window.__adobe_cep__.evalScript(command, function (result) {
        if (result === "EvalScript error.") {
          writeStatus(job.status_path, "error|Premiere rejected the bridge script");
        }
        try { fs.unlinkSync(claimed); } catch (_) {}
        busy = false;
      });
    } catch (error) {
      if (job && job.status_path) writeStatus(job.status_path, "error|" + String(error));
      try { fs.unlinkSync(claimed); } catch (_) {}
      busy = false;
    }
  }

  setInterval(poll, 1000);
  poll();
})();
