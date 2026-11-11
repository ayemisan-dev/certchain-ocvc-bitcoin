(() => {
    "use strict";

    const MAX_COLUMN_HEIGHT = 680;
    const SEMESTER_LABELS = { "1": "1st", "2": "2nd", "3": "3rd", "S": "Summer" };

    const banner = document.getElementById("status-banner");
    const root = document.getElementById("transcript-root");

    const rawData = sessionStorage.getItem("vc_data");
    if (!rawData) {
        banner.className = "banner banner-invalid";
        banner.textContent = "No credential data found.";
        root.innerHTML =
            '<div class="empty-state">Please start a <a href="/">new verification</a>.</div>';
        return;
    }

    let data;
    try {
        data = JSON.parse(rawData);
    } catch (err) {
        console.error("[render] failed to parse vc_data:", err);
        banner.className = "banner banner-invalid";
        banner.textContent = "Failed to read credential data.";
        return;
    }

    const status =
        data.verification_status || (data.verified === true ? "valid" : "invalid");
    const reason = data.reason || null;
    const vc = data.vc || null;

    renderBanner(status, reason);
    if (vc && typeof vc === "object") {
        renderTranscript(vc);
    } else {
        root.innerHTML = `<div class="empty-state">Credential data unavailable...</div>`;
    }

    // --- Banner ------------------------------------------------------------
    function renderBanner(status, reason) {
        const labels = {
            valid: "✓ VERIFIED OFFICIAL CREDENTIAL",
            revoked: "✗ CREDENTIAL HAS BEEN REVOKED",
            invalid: "✗ CREDENTIAL INVALID",
        };
        banner.className = `banner banner-${status}`;
        banner.textContent = labels[status] || labels.invalid;
        if (status !== "valid" && reason) {
            banner.textContent += ` — ${reason}`;
        }
    }

    // --- Transcript --------------------------------------------------------
    function renderTranscript(vc) {
        const subject = vc.credentialSubject || {};
        const achievement = subject.achievement || {};
        const issuer = vc.issuer || {};
        const issuerAddress = issuer.address || {};

        root.innerHTML = `
            <article class="transcript">
                <header class="transcript-header">
                    <img src="/static/images/logo.png" alt="University Logo" class="logo">
                    <h1>${escapeHtml(issuer.name || "")}</h1>
                    <p class="location">${escapeHtml(issuerAddress.addressCountry || "")}</p>
                    <h2>${escapeHtml(issuer.department || "")}</h2>
                </header>

                <div class="photo-box">PHOTO</div>

                <section class="info-grid">
                    ${infoItem("Name", `${subject.givenName || ""} ${subject.familyName || ""}`.trim())}
                    ${infoItem("Student No.", subject.studentId)}
                    ${infoItem("Date of Birth", subject.dateOfBirth)}
                    ${infoItem("Date of Admission", achievement.dateofAdmission)}
                    ${infoItem("Date of Graduation", achievement.dateofGraduation)}
                    ${infoItem("Program", subject.program)}
                    ${infoItem("Degree", achievement.name)}
                </section>

                <section class="transcript-columns">
                    <div class="column" id="col-left"></div>
                    <div class="column" id="col-right"></div>
                </section>

                <footer class="transcript-footer">
                    <div>
                        <p>Date Issued: ${escapeHtml(vc.dateIssued || "")}</p>
                        <p class="signature">_______________________<br>Registrar</p>
                    </div>
                </footer>
            </article>
        `;

        fillColumns(subject.transcriptRecord || [], achievement);
    }

    function fillColumns(semesters, achievement) {
        const left = document.getElementById("col-left");
        const right = document.getElementById("col-right");
        if (!left || !right) return;

        let currentColumn = left;
        let switched = false;

        semesters.forEach((semester) => {
            currentColumn.appendChild(renderSemester(semester));
            if (!switched && left.offsetHeight > MAX_COLUMN_HEIGHT) {
                const mark = document.createElement("div");
                mark.className = "continue-mark";
                mark.textContent = "— continue next column —";
                left.appendChild(mark);
                currentColumn = right;
                switched = true;
            }
        });

        right.appendChild(renderSummary(achievement));
    }

    function renderSemester(semester) {
        const enrollment = semester.enrollmentRecord || [];
        const rows = enrollment
            .map(
                (course) => `
                <tr>
                    <td>${escapeHtml(String(course.courseCode ?? ""))}</td>
                    <td>${escapeHtml(course.courseName || "")}</td>
                    <td class="num">${course.credit ?? ""}</td>
                    <td class="num">${escapeHtml(course.grade || "")}</td>
                </tr>`
            )
            .join("");

        const div = document.createElement("div");
        div.className = "semester";
        div.innerHTML = `
            <h3 class="semester-title">${formatSemester(semester.semester)}</h3>
            <table>
                <thead>
                    <tr><th>Code</th><th>Course Title</th><th class="num">CR</th><th class="num">GRD</th></tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
            <p class="gpa-line">GPS: ${semester.GPS ?? "—"} &nbsp;|&nbsp; GPA: ${semester.GPA ?? "—"}</p>
        `;
        return div;
    }

    function renderSummary(achievement) {
        const div = document.createElement("div");
        div.className = "summary";
        div.innerHTML = `
            <p><strong>GRAND TOTAL CREDITS:</strong> ${achievement.totalCredits ?? "—"}</p>
            <p><strong>GPA:</strong> ${achievement.GPA ?? "—"}</p>
            <p class="closed-mark">— Transcript Closed —</p>
        `;
        return div;
    }

    function formatSemester(value) {
        if (value == null) return "";
        const str = String(value);
        if (!str.includes("/")) return escapeHtml(str);
        const [semester, year] = str.split("/");
        const label = SEMESTER_LABELS[semester] || semester;
        return `${escapeHtml(label)} Semester, ${escapeHtml(year)}`;
    }

    function infoItem(label, value) {
        const display =
            value === undefined || value === null || value === ""
                ? "—"
                : escapeHtml(String(value));
        return `<div class="info-item"><span class="label">${label}:</span> <span class="value">${display}</span></div>`;
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }
})();