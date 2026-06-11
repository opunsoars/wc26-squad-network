(async () => {
  const params = new URLSearchParams(window.location.search);
  const teamCode = params.get("team");
  if (!teamCode) {
    document.getElementById("team-title").textContent = "Team not found";
    return;
  }

  const data = await d3.json(`data/teams/${teamCode}.json`);
  document.getElementById("team-title").textContent = data.squad;
  document.getElementById("team-subtitle").textContent =
    `Density: ${data.metrics.density.toFixed(3)} · Clustering: ${data.metrics.clustering.toFixed(3)} · Avg weighted degree: ${Math.round(data.metrics.avg_weighted_degree)}`;

  const players = data.players.slice().sort((a, b) => b.freshness_minutes - a.freshness_minutes);

  const svg = d3.select("#freshness-bars");
  const margin = { top: 10, right: 20, bottom: 30, left: 160 };
  const width = +svg.attr("width") - margin.left - margin.right;
  const height = Math.max(400, players.length * 20);
  svg.attr("height", height + margin.top + margin.bottom);

  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleLinear().domain([0, d3.max(players, d => d.freshness_minutes) || 1]).range([0, width]).nice();
  const y = d3.scaleBand().domain(players.map(d => d.name)).range([0, height]).padding(0.15);

  const color = d3.scaleSequential(d3.interpolateRdYlGn)
    .domain([d3.min(players, d => d.freshness_minutes), d3.max(players, d => d.freshness_minutes)]);

  g.append("g").attr("class", "axis").call(d3.axisLeft(y));
  g.append("g").attr("class", "axis").attr("transform", `translate(0,${height})`).call(d3.axisBottom(x).ticks(6));

  g.selectAll(".bar").data(players).join("rect")
    .attr("class", "bar")
    .attr("x", 0)
    .attr("y", d => y(d.name))
    .attr("width", d => x(d.freshness_minutes))
    .attr("height", y.bandwidth())
    .attr("fill", d => color(d.freshness_minutes))
    .attr("rx", 3);

  g.selectAll(".bar-label").data(players).join("text")
    .attr("class", "bar-label")
    .attr("x", d => x(d.freshness_minutes) + 4)
    .attr("y", d => y(d.name) + y.bandwidth() / 2 + 4)
    .style("font-size", "10px").style("fill", "#8b949e")
    .text(d => d.freshness_minutes);

  // expose data for network.js
  window._wc26TeamData = data;
})();
