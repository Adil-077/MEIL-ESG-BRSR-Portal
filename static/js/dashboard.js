(function () {

  const fmt = (n) =>
    Number(n).toLocaleString(undefined, {
      maximumFractionDigits: 1
    });

  const orgId = window.ORG_ID;
  const periodId = window.PERIOD_ID;

  fetch(`/api/dashboard-data?org_id=${orgId}&period_id=${periodId}`)

    .then((res) => {
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      return res.json();
    })

    .then((data) => {

      // Existing dashboard
      renderPillarChart(data);
      renderTrendChart(data);
      renderYoyChart(data);
      renderHeadlineKpis(data);

      // ESG Intelligence
      renderCompleteness(data);
      renderAnomalies(data);

    })

    .catch((err) => {
      console.error("Dashboard data load failed:", err);

      const anomalyList = document.getElementById("anomaly-list");

      if (anomalyList) {
        anomalyList.innerHTML = `
          <div class="alert alert-danger small mb-0">
            Unable to load ESG intelligence data.
          </div>
        `;
      }
    });


  // =========================================================
  // EXISTING: E / S / G PILLAR CHART
  // =========================================================

  function renderPillarChart(data) {

    const ctx = document.getElementById("pillarChart");

    if (!ctx) return;

    new Chart(ctx, {

      type: "doughnut",

      data: {

        labels: [
          "Environment (E)",
          "Social (S)",
          "Governance (G)"
        ],

        datasets: [
          {
            data: [
              data.pillar_current.E,
              data.pillar_current.S,
              data.pillar_current.G
            ],

            backgroundColor: [
              "#2E7D32",
              "#1E88E5",
              "#6A1B9A"
            ],

            borderWidth: 0
          }
        ]
      },

      options: {

        plugins: {
          legend: {
            position: "bottom"
          }
        },

        cutout: "60%"
      }
    });
  }


  // =========================================================
  // EXISTING: GHG TREND
  // =========================================================

  function renderTrendChart(data) {

    const ctx = document.getElementById("trendChart");

    if (!ctx) return;

    new Chart(ctx, {

      type: "line",

      data: {

        labels: data.trend_labels,

        datasets: [
          {
            label: "GHG Emissions (tCO2e)",

            data: data.trend_ghg,

            borderColor: "#2E7D32",

            backgroundColor: "rgba(46,125,50,0.15)",

            tension: 0.3,

            fill: true,

            pointRadius: 4
          }
        ]
      },

      options: {

        plugins: {
          legend: {
            display: false
          }
        },

        scales: {
          y: {
            beginAtZero: true
          }
        }
      }
    });
  }


  // =========================================================
  // EXISTING: E / S / G YOY CHART
  // =========================================================

  function renderYoyChart(data) {

    const ctx = document.getElementById("yoyChart");

    if (!ctx) return;

    new Chart(ctx, {

      type: "bar",

      data: {

        labels: [
          "Environment",
          "Social",
          "Governance"
        ],

        datasets: [

          {
            label: data.prior_period_name || "Prior FY",

            data: [
              data.pillar_prior.E,
              data.pillar_prior.S,
              data.pillar_prior.G
            ],

            backgroundColor: "#B0BEC5"
          },

          {
            label: "Current FY",

            data: [
              data.pillar_current.E,
              data.pillar_current.S,
              data.pillar_current.G
            ],

            backgroundColor: "#1F3864"
          }

        ]
      },

      options: {

        plugins: {
          legend: {
            position: "bottom"
          }
        },

        scales: {
          y: {
            beginAtZero: true
          }
        }
      }
    });
  }


  // =========================================================
  // EXISTING: HEADLINE KPIs
  // =========================================================

  function renderHeadlineKpis(data) {

    const map = {

      "kpi-ghg": data.headline.C_P6_GHG,

      "kpi-energy": data.headline.C_P6_ENERGY,

      "kpi-water": data.headline.C_P6_WATER,

      "kpi-csr": data.headline.C_P8_CSR_SPEND

    };

    Object.entries(map).forEach(([id, val]) => {

      const el = document.getElementById(id);

      if (el) {
        el.textContent = fmt(val || 0);
      }

    });
  }


  // =========================================================
  // NEW: DATA COMPLETENESS
  // =========================================================

  function renderCompleteness(data) {

  const completeness = data.completeness;

  if (!completeness) return;

  const percentageEl =
    document.getElementById("completeness-percentage");

  const countEl =
    document.getElementById("completeness-count");

  const barEl =
    document.getElementById("completeness-bar");

  const missingEl =
    document.getElementById("missing-metrics");


  // Percentage
  if (percentageEl) {
    percentageEl.textContent =
      `${completeness.percentage}%`;
  }


  // Reported / total
  if (countEl) {
    countEl.textContent =
      `${completeness.reported} / ${completeness.total} ${
        completeness.scope === "Consolidated metrics"
          ? "consolidated metrics"
          : "required metrics"
      } reported`;
  }


  // Progress bar
  if (barEl) {
    barEl.style.width =
      `${completeness.percentage}%`;

    barEl.setAttribute(
      "aria-valuenow",
      completeness.percentage
    );
  }


  // Missing metrics
  if (missingEl) {

    missingEl.innerHTML = "";

    if (
      !completeness.missing ||
      completeness.missing.length === 0
    ) {

      missingEl.innerHTML = `
        <li class="text-success">
          All required metrics reported
        </li>
      `;

    } else {

      completeness.missing.forEach((metric) => {

        const li =
          document.createElement("li");

        li.className = "text-danger";
        li.textContent = metric;

        missingEl.appendChild(li);
      });
    }
  }
}
  // =========================================================

  function renderAnomalies(data) {

    const anomalies = data.anomalies || [];

    const countEl =
      document.getElementById("anomaly-count");

    const listEl =
      document.getElementById("anomaly-list");


    if (!listEl) return;


    // Number of anomalies
    if (countEl) {

      countEl.textContent =
        `${anomalies.length} detected`;

    }


    // No anomalies
    if (anomalies.length === 0) {

      listEl.innerHTML = `
        <div class="alert alert-success small mb-0">
          <i class="fa-solid fa-circle-check me-1"></i>
          No significant year-on-year anomalies detected.
        </div>
      `;

      return;
    }


    // Clear loading message
    listEl.innerHTML = "";


    anomalies.forEach((item) => {

      const severity = item.severity || "MODERATE";

      let badgeClass = "bg-secondary";

      if (severity === "CRITICAL") {
        badgeClass = "bg-danger";
      } else if (severity === "HIGH") {
        badgeClass = "bg-warning text-dark";
      } else if (severity === "MODERATE") {
        badgeClass = "bg-info text-dark";
      }


      const changeValue =
        item.change_percentage !== null &&
        item.change_percentage !== undefined
          ? `${item.change_percentage > 0 ? "+" : ""}${fmt(item.change_percentage)}%`
          : "—";


      const directionIcon =
        item.direction === "increase"
          ? "fa-arrow-up"
          : item.direction === "decrease"
            ? "fa-arrow-down"
            : "fa-minus";


      const directionClass =
        item.direction === "increase"
          ? "text-danger"
          : item.direction === "decrease"
            ? "text-success"
            : "text-muted";


      const div = document.createElement("div");

      div.className =
        "border rounded p-3 mb-2";


    div.innerHTML = `
  <div class="d-flex justify-content-between align-items-start">
    <div>
      <div class="fw-bold">
        ${item.name}
      </div>

      <div class="small text-muted mt-1">
        ${fmt(item.previous_value)}
        ${item.unit || ""}
        →
        ${fmt(item.current_value)}
        ${item.unit || ""}
      </div>
    </div>

    <span class="badge ${badgeClass}">
      ${severity}
    </span>
  </div>

  <div class="mt-2">
    <span class="${directionClass} fw-bold">
      <i class="fa-solid ${directionIcon} me-1"></i>
      ${changeValue}
    </span>

    <span class="small text-muted ms-2">
      ${item.previous_period}
      →
      ${item.current_period}
    </span>
  </div>

  <div class="small text-muted mt-1">
    ${item.reason || "Significant year-on-year change detected."}
  </div>

  <div class="mt-2 p-2 rounded bg-light small">
    <strong>
      <i class="fa-solid fa-circle-info me-1"></i>
      Recommended action:
    </strong>
    ${item.recommendation || "Review the underlying ESG records and supporting evidence."}
  </div>

  <div class="mt-2">
    <a
      href="/esg/${orgId}/${periodId}#metric-${item.code}"
      class="btn btn-sm btn-outline-primary"
    >
      <i class="fa-solid fa-magnifying-glass me-1"></i>
      Investigate
    </a>
  </div>
`;

      listEl.appendChild(div);
    });
  }

})();