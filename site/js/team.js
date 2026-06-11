(async () => {
  const params = new URLSearchParams(window.location.search);
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

  document.title = `${data.squad} — WC26`;
  document.getElementById("team-title").textContent = data.squad;

  const m = data.metrics;
  const playerCount = data.players.length;
  const withMinutes = data.players.filter(p => p.freshness_minutes > 0).length;
  const avgFresh = Math.round(data.players.reduce((s, p) => s + p.freshness_minutes, 0) / playerCount);

  document.getElementById("team-subtitle").innerHTML =
    `Network density: <strong>${m.density.toFixed(3)}</strong> &nbsp;·&nbsp; ` +
    `Clustering: <strong>${m.clustering.toFixed(3)}</strong> &nbsp;·&nbsp; ` +
    `${withMinutes}/${playerCount} players with minutes in window &nbsp;·&nbsp; ` +
    `Avg freshness: <strong>${avgFresh.toLocaleString()} min</strong>`;

  // Freshness bar chart
  const players = data.players.slice().sort((a, b) => b.freshness_minutes - a.freshness_minutes);

  const container = document.getElementById("freshness-bars").parentElement;
  const containerWidth = container.offsetWidth - 48; // subtract padding
  const barHeight = 22;
  const margin = { top: 10, right: 80, bottom: 30, left: 160 };
  const width = containerWidth - margin.left - margin.right;
  const height = players.length * barHeight;

  const svg = d3.select("#freshness-bars")
    .attr("width", containerWidth)
    .attr("height", height + margin.top + margin.bottom);

  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const maxMin = d3.max(players, d => d.freshness_minutes) || 1;
  const x = d3.scaleLinear().domain([0, maxMin]).range([0, width]).nice();
  const y = d3.scaleBand().domain(players.map(d => d.name)).range([0, height]).padding(0.18);

  const color = d3.scaleSequential(d3.interpolateRdYlGn).domain([0, maxMin]);

  g.append("g").attr("class", "axis")
    .call(d3.axisLeft(y).tickSize(0))
    .call(ax => ax.select(".domain").remove());

  g.append("g").attr("class", "axis")
    .attr("transform", `translate(0,${height})`)
    .call(d3.axisBottom(x).ticks(5).tickFormat(d => `${(d/60).toFixed(0)}h`))
    .call(ax => ax.select(".domain").remove());

  // Position colour strip on left of bar
  const posColor = { GK: "#f0b429", DF: "#4dabf7", MF: "#69db7c", FW: "#ff6b6b" };

  g.selectAll(".pos-dot").data(players).join("circle")
    .attr("class", "pos-dot")
    .attr("cx", -8)
    .attr("cy", d => y(d.name) + y.bandwidth() / 2)
    .attr("r", 4)
    .attr("fill", d => posColor[d.position] || "#8b949e");

  g.selectAll(".bar").data(players).join("rect")
    .attr("class", "bar")
    .attr("x", 0)
    .attr("y", d => y(d.name))
    .attr("width", d => Math.max(x(d.freshness_minutes), d.freshness_minutes > 0 ? 2 : 0))
    .attr("height", y.bandwidth())
    .attr("fill", d => color(d.freshness_minutes))
    .attr("rx", 3);

  g.selectAll(".bar-label").data(players).join("text")
    .attr("class", "bar-label")
    .attr("x", d => x(d.freshness_minutes) + 6)
    .attr("y", d => y(d.name) + y.bandwidth() / 2 + 1)
    .attr("dominant-baseline", "middle")
    .style("font-size", "10px")
    .style("fill", "#8b949e")
    .text(d => d.freshness_minutes > 0 ? `${d.freshness_minutes.toLocaleString()}` : "no data");

  // network.js is loaded before this script and defines renderNetwork globally
  if (typeof renderNetwork === "function") renderNetwork(data);
})();
