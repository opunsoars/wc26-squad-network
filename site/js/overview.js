(async () => {
  const summary = await d3.json("data/summary.json");
  const squads = summary.squads.sort((a, b) => b.avg_freshness_minutes - a.avg_freshness_minutes);

  // Freshness bar chart
  const svg = d3.select("#freshness-bar");
  const margin = { top: 10, right: 20, bottom: 100, left: 60 };
  const width = +svg.attr("width") - margin.left - margin.right;
  const height = +svg.attr("height") - margin.top - margin.bottom;
  const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const x = d3.scaleBand().domain(squads.map(d => d.squad)).range([0, width]).padding(0.2);
  const y = d3.scaleLinear().domain([0, d3.max(squads, d => d.avg_freshness_minutes)]).range([height, 0]).nice();

  const color = d3.scaleSequential(d3.interpolateRdYlGn)
    .domain([d3.min(squads, d => d.avg_freshness_minutes), d3.max(squads, d => d.avg_freshness_minutes)]);

  g.append("g").attr("class", "axis").attr("transform", `translate(0,${height})`).call(d3.axisBottom(x))
    .selectAll("text").attr("transform", "rotate(-45)").style("text-anchor", "end");
  g.append("g").attr("class", "axis").call(d3.axisLeft(y).ticks(6));

  g.selectAll(".bar").data(squads).join("rect")
    .attr("class", "bar")
    .attr("x", d => x(d.squad))
    .attr("y", d => y(d.avg_freshness_minutes))
    .attr("width", x.bandwidth())
    .attr("height", d => height - y(d.avg_freshness_minutes))
    .attr("fill", d => color(d.avg_freshness_minutes))
    .attr("rx", 3)
    .style("cursor", "pointer")
    .on("click", (_, d) => { window.location.href = `team.html?team=${d.team_code}`; });

  // Scatter: density vs freshness
  const svg2 = d3.select("#scatter");
  const m2 = { top: 20, right: 20, bottom: 50, left: 60 };
  const w2 = +svg2.attr("width") - m2.left - m2.right;
  const h2 = +svg2.attr("height") - m2.top - m2.bottom;
  const g2 = svg2.append("g").attr("transform", `translate(${m2.left},${m2.top})`);

  const xs = d3.scaleLinear().domain(d3.extent(squads, d => d.avg_freshness_minutes)).range([0, w2]).nice();
  const ys = d3.scaleLinear().domain(d3.extent(squads, d => d.density)).range([h2, 0]).nice();

  g2.append("g").attr("class", "axis").attr("transform", `translate(0,${h2})`).call(d3.axisBottom(xs));
  g2.append("g").attr("class", "axis").call(d3.axisLeft(ys).ticks(6));

  g2.selectAll("circle").data(squads).join("circle")
    .attr("cx", d => xs(d.avg_freshness_minutes))
    .attr("cy", d => ys(d.density))
    .attr("r", 5)
    .attr("fill", "#58a6ff")
    .attr("fill-opacity", 0.7)
    .style("cursor", "pointer")
    .on("click", (_, d) => { window.location.href = `team.html?team=${d.team_code}`; });

  g2.selectAll(".label").data(squads).join("text")
    .attr("class", "label")
    .attr("x", d => xs(d.avg_freshness_minutes) + 7)
    .attr("y", d => ys(d.density) + 4)
    .style("font-size", "10px").style("fill", "#8b949e")
    .text(d => d.squad);

  // Squad grid cards
  const grid = d3.select("#squad-grid");
  squads.forEach(d => {
    grid.append("div").attr("class", "squad-card")
      .on("click", () => { window.location.href = `team.html?team=${d.team_code}`; })
      .html(`
        <div class="name">${d.squad}</div>
        <div class="stat">Avg minutes: ${Math.round(d.avg_freshness_minutes)}</div>
        <div class="stat">Network density: ${d.density.toFixed(3)}</div>
      `);
  });
})();
