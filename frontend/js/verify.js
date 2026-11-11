(() => {
    "use strict";

    const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB

    const state = { mode: "upload", file: null };

    const els = {
        status: document.getElementById("status"),
        verifyBtn: document.getElementById("verify-btn"),
        fileInput: document.getElementById("file-input"),
        fileName: document.getElementById("file-name"),
        fingerprint: document.getElementById("fingerprint-input"),
        tabs: document.querySelectorAll(".tab"),
        panels: document.querySelectorAll(".panel"),
    };

    // --- Tab switching -----------------------------------------------------
    els.tabs.forEach((tab) => {
        tab.addEventListener("click", () => switchMode(tab.dataset.mode));
    });

    function switchMode(mode) {
        state.mode = mode;
        els.tabs.forEach((tab) => {
            const active = tab.dataset.mode === mode;
            tab.classList.toggle("active", active);
            tab.setAttribute("aria-selected", String(active));
        });
        els.panels.forEach((panel) => panel.classList.remove("active"));
        const panel = document.getElementById(`${mode}-panel`);
        if (panel) panel.classList.add("active");
        setStatus("");
    }

    // --- File selection ----------------------------------------------------
    els.fileInput.addEventListener("change", () => {
        const file = els.fileInput.files[0];
        if (!file) return;
        if (file.size > MAX_FILE_SIZE) {
            setStatus("File exceeds the 10 MB limit.", "error");
            els.fileInput.value = "";
            state.file = null;
            els.fileName.textContent = "";
            return;
        }
        state.file = file;
        els.fileName.textContent = `Selected: ${file.name}`;
        setStatus("");
    });

    // --- Submit ------------------------------------------------------------
    els.verifyBtn.addEventListener("click", runVerify);

    async function runVerify() {
        sessionStorage.removeItem("vc_data");
        els.verifyBtn.disabled = true;
        setStatus("Verifying...", "info");

        try {
            const response =
                state.mode === "upload" ? await submitFile() : await submitText();
            const result = await response.json().catch(() => ({}));
            handleResult(response.status, result);
        } catch (err) {
            console.error("[verify] network error:", err);
            setStatus("Cannot reach the verification server.", "error");
        } finally {
            els.verifyBtn.disabled = false;
        }
    }

    async function submitFile() {
        if (!state.file) {
            throw new Error("No file selected");
        }
        const formData = new FormData();
        formData.append("file", state.file);
        return fetch("/api/verify", { method: "POST", body: formData });
    }

    async function submitText() {
        const value = els.fingerprint.value.trim();
        if (!value) {
            throw new Error("Fingerprint is empty");
        }
        return fetch("/api/verify", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ fingerprint: value }),
        });
    }

    function handleResult(httpStatus, result) {
        const status =
            result.verification_status ||
            (result.verified === true ? "valid" : "invalid");

        // Both valid and revoked credentials are shown on the result page.
        if ((status === "valid" || status === "revoked") && result.vc) {
            sessionStorage.setItem("vc_data", JSON.stringify(result));
            window.location.href = "/result.html";
            return;
        }

        // Invalid: show the reason inline.
        const reason = result.reason || `Verification failed (HTTP ${httpStatus}).`;
        setStatus(reason, "error");
    }

    function setStatus(message, kind = "") {
        els.status.textContent = message;
        els.status.className = "status" + (kind ? ` status-${kind}` : "");
    }
})();