(function () {
  const fmt = (n) => Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 });

  fetch(`/api/dashboard-data?org_id=${ORG_ID}&period_id=${PERIOD_ID}`)
    .then((res) => res.json())
    .then((data) => {
      renderPillarChart(data);
      renderTrendChart(data);
      renderYoyChart(data);
      renderHeadlineKpis(data);
    })
    .catch((err) => console.error("Dashboard data load failed:", err));

  function renderPillarChart(data) {
    const ctx = document.getElementById("pillarChart");
    if (!ctx) return;
    new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: ["Environment (E)", "Social (S)", "Governance (G)"],
        datasets: [
          {
            data: [data.pillar_current.E, data.pillar_current.S, data.pillar_current.G],
            backgroundColor: ["#2E7D32", "#1E88E5", "#6A1B9A"],
            borderWidth: 0,
          },
        ],
      },
      options: {
        plugins: { legend: { position: "bottom" } },
        cutout: "60%",
      },
    });
  }

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
            pointRadius: 4,
          },
        ],
      },
      options: {
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true } },
      },
    });
  }

  function renderYoyChart(data) {
    const ctx = document.getElementById("yoyChart");
    if (!ctx) return;
    new Chart(ctx, {
      type: "bar",
      data: {
        labels: ["Environment", "Social", "Governance"],
        datasets: [
          {
            label: data.prior_period_name || "Prior FY",
            data: [data.pillar_prior.E, data.pillar_prior.S, data.pillar_prior.G],
            backgroundColor: "#B0BEC5",
          },
          {
            label: "Current FY",
            data: [data.pillar_current.E, data.pillar_current.S, data.pillar_current.G],
            backgroundColor: "#1F3864",
          },
        ],
      },
      options: {
        plugins: { legend: { position: "bottom" } },
        scales: { y: { beginAtZero: true } },
      },
    });
  }

  function renderHeadlineKpis(data) {
    const map = {
      "kpi-ghg": data.headline.C_P6_GHG,
      "kpi-energy": data.headline.C_P6_ENERGY,
      "kpi-water": data.headline.C_P6_WATER,
      "kpi-csr": data.headline.C_P8_CSR_SPEND,
    };
    Object.entries(map).forEach(([id, val]) => {
      const el = document.getElementById(id);
      if (el) el.textContent = fmt(val || 0);
    });
  }
})();
