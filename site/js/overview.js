(async () => {
  const summary = await d3.json("data/summary.json");
  const squads  = summary.squads.sort((a, b) => b.avg_freshness_minutes - a.avg_freshness_minutes);

  const cw = document.querySelector(".chart-container").offsetWidth - 48;

  // ── Freshness bar chart ────────────────────────────────────────────────────
  const bMargin = { top: 8, right: 10, bottom: 90, left: 8 };
  const bw = cw - bMargin.left - bMargin.right;
  const bh = 280;

  const svgBar = d3.select("#freshness-bar")
    .attr("width", cw)
    .attr("height", bh + bMargin.top + bMargin.bottom);

  const gb = svgBar.append("g").attr("transform", `translate(${bMargin.left},${bMargin.top})`);

  const xb    = d3.scaleBand().domain(squads.map(d => d.squad)).range([0, bw]).padding(0.12);
  const yb    = d3.scaleLinear().domain([0, d3.max(squads, d => d.avg_freshness_minutes)]).range([bh, 0]).nice();
  const color = d3.scaleSequential()
    .domain([d3.min(squads, d => d.avg_freshness_minutes), d3.max(squads, d => d.avg_freshness_minutes)])
    .interpolator(d3.interpolateRgb("#f7d7cc", "#d4380d"));

  // Grid
  gb.append("g").attr("class", "grid")
    .call(d3.axisLeft(yb).ticks(4).tickSize(-bw).tickFormat(""))
    .call(ax => ax.select(".domain").remove())
    .selectAll("line").style("stroke", "#e5e2db").style("stroke-dasharray", "2,3");

  gb.append("g").attr("class", "axis").attr("transform", `translate(0,${bh})`)
    .call(d3.axisBottom(xb).tickSize(0))
    .call(ax => ax.select(".domain").remove())
    .selectAll("text")
      .attr("transform", "rotate(-45)")
      .style("text-anchor", "end")
      .style("font-size", "9px")
      .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
      .style("fill", "#5c5a56");

  gb.append("g").attr("class", "axis")
    .call(d3.axisLeft(yb).ticks(4).tickFormat(d => `${Math.round(d / 60)}h`))
    .call(ax => ax.select(".domain").remove())
    .selectAll("text")
      .style("font-size", "10px")
      .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
      .style("fill", "#9a9891");

  gb.selectAll(".bar").data(squads).join("rect")
    .attr("class", "bar")
    .attr("x", d => xb(d.squad))
    .attr("y", d => yb(d.avg_freshness_minutes))
    .attr("width", xb.bandwidth())
    .attr("height", d => bh - yb(d.avg_freshness_minutes))
    .attr("fill", d => color(d.avg_freshness_minutes))
    .attr("rx", 1)
    .style("cursor", "pointer")
    .on("click", (_, d) => { window.location.href = `team.html?team=${d.team_code}`; })
    .append("title").text(d => `${d.squad}: ${Math.round(d.avg_freshness_minutes / 60)}h avg freshness`);

  // ── Scatter: freshness vs density ─────────────────────────────────────────
  const sMargin = { top: 20, right: 24, bottom: 50, left: 55 };
  const sw = cw - sMargin.left - sMargin.right;
  const sh = 360;

  const svgS = d3.select("#scatter")
    .attr("width", cw)
    .attr("height", sh + sMargin.top + sMargin.bottom);

  const gs = svgS.append("g").attr("transform", `translate(${sMargin.left},${sMargin.top})`);

  const xs = d3.scaleLinear().domain(d3.extent(squads, d => d.avg_freshness_minutes)).range([0, sw]).nice();
  const ys = d3.scaleLinear().domain(d3.extent(squads, d => d.density)).range([sh, 0]).nice();

  // Grid
  gs.append("g").attr("class", "grid")
    .call(d3.axisLeft(ys).ticks(5).tickSize(-sw).tickFormat(""))
    .call(ax => ax.select(".domain").remove())
    .selectAll("line").style("stroke", "#e5e2db").style("stroke-dasharray", "2,3");
  gs.append("g").attr("class", "grid")
    .call(d3.axisBottom(xs).ticks(6).tickSize(sh).tickFormat(""))
    .call(ax => ax.select(".domain").remove())
    .selectAll("line").attr("transform", "translate(0,-" + sh + ")").style("stroke", "#e5e2db").style("stroke-dasharray", "2,3");

  gs.append("g").attr("class", "axis").attr("transform", `translate(0,${sh})`)
    .call(d3.axisBottom(xs).ticks(6).tickFormat(d => `${Math.round(d / 60)}h`))
    .call(ax => ax.select(".domain").remove())
    .selectAll("text").style("font-size", "10px")
      .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
      .style("fill", "#9a9891");

  gs.append("g").attr("class", "axis")
    .call(d3.axisLeft(ys).ticks(5))
    .call(ax => ax.select(".domain").remove())
    .selectAll("text").style("font-size", "10px")
      .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
      .style("fill", "#9a9891");

  gs.append("text").attr("x", sw / 2).attr("y", sh + 42)
    .attr("text-anchor", "middle").style("font-size", "10px")
    .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
    .style("fill", "#9a9891").text("Avg player freshness — hours played in last 365 days");

  gs.append("text").attr("transform", "rotate(-90)").attr("x", -sh / 2).attr("y", -42)
    .attr("text-anchor", "middle").style("font-size", "10px")
    .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
    .style("fill", "#9a9891").text("Network density");

  const dots = gs.selectAll(".dot").data(squads).join("g")
    .attr("class", "dot").style("cursor", "pointer")
    .on("click", (_, d) => { window.location.href = `team.html?team=${d.team_code}`; });

  dots.append("circle")
    .attr("cx", d => xs(d.avg_freshness_minutes))
    .attr("cy", d => ys(d.density))
    .attr("r", 5.5)
    .attr("fill", "#d4380d")
    .attr("fill-opacity", 0.65)
    .attr("stroke", "#d4380d")
    .attr("stroke-opacity", 0.25)
    .attr("stroke-width", 4);

  dots.append("text")
    .attr("x", d => xs(d.avg_freshness_minutes))
    .attr("y", d => ys(d.density))
    .attr("dx", d => xs(d.avg_freshness_minutes) > sw * 0.75 ? -8 : 9)
    .attr("dy", d => ys(d.density) < sh * 0.2 ? 13 : -5)
    .attr("text-anchor", d => xs(d.avg_freshness_minutes) > sw * 0.75 ? "end" : "start")
    .style("font-size", "9px")
    .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
    .style("fill", "#5c5a56")
    .text(d => d.squad);

  // Hover
  const tip = d3.select("body").append("div")
    .style("position", "absolute").style("background", "#ffffff")
    .style("border", "1px solid #c9c6be").style("border-radius", "3px")
    .style("padding", "0.45rem 0.7rem").style("font-size", "12px")
    .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
    .style("pointer-events", "none").style("opacity", 0).style("z-index", "100")
    .style("box-shadow", "0 2px 8px rgba(0,0,0,0.1)");

  dots
    .on("mouseover", (event, d) => {
      d3.select(event.currentTarget).select("circle").attr("fill-opacity", 1);
      tip.transition().duration(80).style("opacity", 1);
      tip.html(`<strong style="color:#1a1917">${d.flag || ""} ${d.squad}</strong><br/>
        <span style="color:#9a9891">Avg freshness:</span> <span style="color:#1a1917">${Math.round(d.avg_freshness_minutes / 60)}h</span><br/>
        <span style="color:#9a9891">Density:</span> <span style="color:#1a1917">${d.density.toFixed(3)}</span>`)
        .style("left", `${event.pageX + 12}px`).style("top", `${event.pageY - 10}px`);
    })
    .on("mousemove", event => tip.style("left", `${event.pageX + 12}px`).style("top", `${event.pageY - 10}px`))
    .on("mouseout", event => {
      d3.select(event.currentTarget).select("circle").attr("fill-opacity", 0.65);
      tip.transition().duration(150).style("opacity", 0);
    });

  // ── Squad grid cards ──────────────────────────────────────────────────────
  const maxFresh = d3.max(squads, d => d.avg_freshness_minutes);
  const grid = d3.select("#squad-grid");

  squads.forEach((d, i) => {
    const pct = Math.round((d.avg_freshness_minutes / maxFresh) * 100);
    grid.append("div").attr("class", "squad-card")
      .on("click", () => { window.location.href = `team.html?team=${d.team_code}`; })
      .html(`
        <div class="card-rank">#${i + 1}</div>
        <div class="card-flag">${d.flag || ""}</div>
        <div class="card-name">${d.squad}</div>
        <div class="card-bar-bg"><div class="card-bar-fill" style="width:${pct}%"></div></div>
        <div class="card-stats">
          <span>${Math.round(d.avg_freshness_minutes / 60)}h avg</span>
          <span>density ${d.density.toFixed(2)}</span>
        </div>
      `);
  });
})();
