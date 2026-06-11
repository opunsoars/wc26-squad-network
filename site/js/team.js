(async () => {
  const params   = new URLSearchParams(window.location.search);
  const teamCode = params.get("team");
  if (!teamCode) {
    document.getElementById("team-title").textContent = "Team not found";
    return;
  }

  let data;
  try {
    data = await d3.json(`data/teams/${teamCode}.json`);
  } catch (e) {
    document.getElementById("team-title").textContent = "Team not found";
    return;
  }

  document.title = `${data.squad} — WC26 Squad Networks`;

  const flag = data.flag || "";
  document.getElementById("team-title").textContent = `${flag} ${data.squad}`.trim();

  const m           = data.metrics;
  const playerCount = data.players.length;
  const withMinutes = data.players.filter(p => p.freshness_minutes > 0).length;
  const avgFresh    = Math.round(data.players.reduce((s, p) => s + p.freshness_minutes, 0) / playerCount);

  document.getElementById("team-subtitle").innerHTML =
    `Network density: <strong>${m.density.toFixed(3)}</strong> &nbsp;·&nbsp; ` +
    `Clustering: <strong>${m.clustering.toFixed(3)}</strong> &nbsp;·&nbsp; ` +
    `${withMinutes}/${playerCount} players with minutes &nbsp;·&nbsp; ` +
    `Avg freshness: <strong>${Math.round(avgFresh / 60)}h</strong>`;

  // ── Freshness bar chart ──────────────────────────────────────────────────────
  const players = data.players.slice().sort((a, b) => b.freshness_minutes - a.freshness_minutes);

  const container    = document.getElementById("freshness-bars").parentElement;
  const cw           = container.offsetWidth - 48;
  const barHeight    = 22;
  const margin       = { top: 8, right: 70, bottom: 28, left: 170 };
  const chartW       = cw - margin.left - margin.right;
  const chartH       = players.length * barHeight;

  const svg = d3.select("#freshness-bars")
    .attr("width", cw)
    .attr("height", chartH + margin.top + margin.bottom);

  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const maxMin = d3.max(players, d => d.freshness_minutes) || 1;
  const x      = d3.scaleLinear().domain([0, maxMin]).range([0, chartW]).nice();
  const y      = d3.scaleBand().domain(players.map(d => d.name)).range([0, chartH]).padding(0.2);

  // Subtle grid lines
  g.append("g").attr("class", "grid")
    .call(d3.axisBottom(x).ticks(5).tickSize(chartH).tickFormat(""))
    .call(ax => ax.select(".domain").remove())
    .call(ax => ax.selectAll(".tick line").attr("y1", -chartH).attr("stroke", "#e5e2db").attr("stroke-dasharray", "2,3"));

  g.append("g").attr("class", "axis")
    .call(d3.axisLeft(y).tickSize(0))
    .call(ax => ax.select(".domain").remove())
    .selectAll("text").style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
                      .style("font-size", "11px").style("fill", "#1a1917");

  g.append("g").attr("class", "axis")
    .attr("transform", `translate(0,${chartH})`)
    .call(d3.axisBottom(x).ticks(5).tickFormat(d => `${Math.round(d / 60)}h`))
    .call(ax => ax.select(".domain").remove())
    .selectAll("text").style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
                      .style("font-size", "10px").style("fill", "#9a9891");

  const posColor = { GK: "#d48b07", DF: "#1a5fa8", MF: "#2d7a3f", FW: "#c0362c" };

  // Position dot left of label
  g.selectAll(".pos-dot").data(players).join("circle")
    .attr("class", "pos-dot")
    .attr("cx", -10)
    .attr("cy", d => y(d.name) + y.bandwidth() / 2)
    .attr("r", 4)
    .attr("fill", d => posColor[d.position] || "#9a9891")
    .attr("fill-opacity", 0.85);

  // Bar fill — single accent colour scaled by freshness
  const barFill = d3.scaleSequential()
    .domain([0, maxMin])
    .interpolator(d3.interpolateRgb("#f7d7cc", "#d4380d"));

  g.selectAll(".bar").data(players).join("rect")
    .attr("class", "bar")
    .attr("x", 0)
    .attr("y", d => y(d.name))
    .attr("width", d => Math.max(x(d.freshness_minutes), d.freshness_minutes > 0 ? 2 : 0))
    .attr("height", y.bandwidth())
    .attr("fill", d => d.freshness_minutes > 0 ? barFill(d.freshness_minutes) : "#e5e2db")
    .attr("rx", 1);

  g.selectAll(".bar-label").data(players).join("text")
    .attr("class", "bar-label")
    .attr("x", d => x(d.freshness_minutes) + 5)
    .attr("y", d => y(d.name) + y.bandwidth() / 2 + 1)
    .attr("dominant-baseline", "middle")
    .style("font-size", "10px")
    .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
    .style("fill", "#9a9891")
    .text(d => d.freshness_minutes > 0
      ? `${d.freshness_minutes.toLocaleString()}`
      : "no data in window");

  if (typeof renderNetwork === "function") renderNetwork(data);
})();
