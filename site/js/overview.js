(async () => {
  const summary = await d3.json("data/summary.json");
  const squads = summary.squads.sort((a, b) => b.avg_freshness_minutes - a.avg_freshness_minutes);

  const containerWidth = document.querySelector(".chart-container").offsetWidth - 48;

  // ── Freshness bar chart ────────────────────────────────────────────────────
  const margin = { top: 10, right: 20, bottom: 90, left: 10 };
  const bw = containerWidth - margin.left - margin.right;
  const bh = 320;

  const svgBar = d3.select("#freshness-bar")
    .attr("width", containerWidth)
    .attr("height", bh + margin.top + margin.bottom);

  const gb = svgBar.append("g").attr("transform", `translate(${margin.left},${margin.top})`);

  const xb = d3.scaleBand().domain(squads.map(d => d.squad)).range([0, bw]).padding(0.15);
  const yb = d3.scaleLinear().domain([0, d3.max(squads, d => d.avg_freshness_minutes)]).range([bh, 0]).nice();
  const color = d3.scaleSequential(d3.interpolateRdYlGn)
    .domain([d3.min(squads, d => d.avg_freshness_minutes), d3.max(squads, d => d.avg_freshness_minutes)]);

  gb.append("g").attr("class", "axis").attr("transform", `translate(0,${bh})`)
    .call(d3.axisBottom(xb).tickSize(0))
    .call(ax => ax.select(".domain").remove())
    .selectAll("text")
      .attr("transform", "rotate(-45)")
      .style("text-anchor", "end")
      .style("font-size", "10px");

  gb.append("g").attr("class", "axis")
    .call(d3.axisLeft(yb).ticks(5).tickFormat(d => `${Math.round(d/60)}h`))
    .call(ax => ax.select(".domain").remove());

  gb.selectAll(".bar").data(squads).join("rect")
    .attr("class", "bar")
    .attr("x", d => xb(d.squad))
    .attr("y", d => yb(d.avg_freshness_minutes))
    .attr("width", xb.bandwidth())
    .attr("height", d => bh - yb(d.avg_freshness_minutes))
    .attr("fill", d => color(d.avg_freshness_minutes))
    .attr("rx", 2)
    .style("cursor", "pointer")
    .on("click", (_, d) => { window.location.href = `team.html?team=${d.team_code}`; })
    .append("title").text(d => `${d.squad}\n${Math.round(d.avg_freshness_minutes).toLocaleString()} min avg`);

  // ── Scatter: freshness vs density ─────────────────────────────────────────
  const m2 = { top: 20, right: 20, bottom: 50, left: 55 };
  const w2 = containerWidth - m2.left - m2.right;
  const h2 = 380;

  const svgS = d3.select("#scatter")
    .attr("width", containerWidth)
    .attr("height", h2 + m2.top + m2.bottom);

  const g2 = svgS.append("g").attr("transform", `translate(${m2.left},${m2.top})`);

  const xs = d3.scaleLinear().domain(d3.extent(squads, d => d.avg_freshness_minutes)).range([0, w2]).nice();
  const ys = d3.scaleLinear().domain(d3.extent(squads, d => d.density)).range([h2, 0]).nice();

  // Grid lines
  g2.append("g").attr("class", "grid")
    .call(d3.axisLeft(ys).ticks(5).tickSize(-w2).tickFormat(""))
    .call(ax => ax.select(".domain").remove())
    .selectAll("line").style("stroke", "#21262d").style("stroke-dasharray", "3,3");

  g2.append("g").attr("class", "axis").attr("transform", `translate(0,${h2})`)
    .call(d3.axisBottom(xs).ticks(6).tickFormat(d => `${Math.round(d/60)}h`))
    .call(ax => ax.select(".domain").remove());

  g2.append("g").attr("class", "axis")
    .call(d3.axisLeft(ys).ticks(5))
    .call(ax => ax.select(".domain").remove());

  g2.append("text").attr("x", w2 / 2).attr("y", h2 + 40)
    .attr("text-anchor", "middle").style("font-size", "11px").style("fill", "#8b949e")
    .text("Avg player freshness (hours played in last 365 days)");

  g2.append("text").attr("transform", "rotate(-90)").attr("x", -h2 / 2).attr("y", -40)
    .attr("text-anchor", "middle").style("font-size", "11px").style("fill", "#8b949e")
    .text("Network density");

  const dots = g2.selectAll(".dot").data(squads).join("g")
    .attr("class", "dot")
    .style("cursor", "pointer")
    .on("click", (_, d) => { window.location.href = `team.html?team=${d.team_code}`; });

  dots.append("circle")
    .attr("cx", d => xs(d.avg_freshness_minutes))
    .attr("cy", d => ys(d.density))
    .attr("r", 6)
    .attr("fill", "#58a6ff")
    .attr("fill-opacity", 0.75)
    .attr("stroke", "#58a6ff")
    .attr("stroke-opacity", 0.3)
    .attr("stroke-width", 4);

  // Smart label placement: offset by quadrant to avoid overlap
  dots.append("text")
    .attr("x", d => xs(d.avg_freshness_minutes))
    .attr("y", d => ys(d.density))
    .attr("dx", d => xs(d.avg_freshness_minutes) > w2 * 0.75 ? -8 : 10)
    .attr("dy", d => ys(d.density) < h2 * 0.2 ? 14 : -6)
    .attr("text-anchor", d => xs(d.avg_freshness_minutes) > w2 * 0.75 ? "end" : "start")
    .style("font-size", "10px")
    .style("fill", "#8b949e")
    .text(d => d.squad);

  // Hover tooltip
  const tip = d3.select("body").append("div")
    .style("position", "absolute").style("background", "#161b22")
    .style("border", "1px solid #30363d").style("border-radius", "6px")
    .style("padding", "0.5rem 0.75rem").style("font-size", "12px")
    .style("pointer-events", "none").style("opacity", 0).style("z-index", "100");

  dots
    .on("mouseover", (event, d) => {
      d3.select(event.currentTarget).select("circle").attr("fill", "#f0b429");
      tip.transition().duration(100).style("opacity", 1);
      tip.html(`<strong style="color:#e6edf3">${d.squad}</strong><br/>
        <span style="color:#8b949e">Avg freshness:</span> ${Math.round(d.avg_freshness_minutes/60)}h<br/>
        <span style="color:#8b949e">Density:</span> ${d.density.toFixed(3)}`)
        .style("left", `${event.pageX + 12}px`).style("top", `${event.pageY - 10}px`);
    })
    .on("mousemove", event => tip.style("left", `${event.pageX + 12}px`).style("top", `${event.pageY - 10}px`))
    .on("mouseout", (event) => {
      d3.select(event.currentTarget).select("circle").attr("fill", "#58a6ff");
      tip.transition().duration(200).style("opacity", 0);
    });

  // ── Squad grid cards ───────────────────────────────────────────────────────
  const maxFresh = d3.max(squads, d => d.avg_freshness_minutes);
  const grid = d3.select("#squad-grid");

  squads.forEach((d, i) => {
    const rank = i + 1;
    const pct = Math.round((d.avg_freshness_minutes / maxFresh) * 100);
    grid.append("div").attr("class", "squad-card")
      .on("click", () => { window.location.href = `team.html?team=${d.team_code}`; })
      .html(`
        <div class="card-rank">#${rank}</div>
        <div class="card-name">${d.squad}</div>
        <div class="card-bar-bg"><div class="card-bar-fill" style="width:${pct}%;background:${color(d.avg_freshness_minutes)}"></div></div>
        <div class="card-stats">
          <span>${Math.round(d.avg_freshness_minutes / 60)}h avg</span>
          <span>density ${d.density.toFixed(2)}</span>
        </div>
      `);
  });
})();
