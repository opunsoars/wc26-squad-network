function renderNetwork(data) {
  const svgEl = document.getElementById("network");
  if (!svgEl || !data) return;

  const width = 900;
  const height = 520;
  svgEl.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svgEl.setAttribute("width", "100%");
  svgEl.setAttribute("height", height);
  svgEl.style.display = "block";
  svgEl.style.background = "#faf9f7";

  const svg = d3.select("#network");
  svg.selectAll("*").remove();

  const nodes = data.players.map(p => ({
    id: p.tm_id,
    name: p.name,
    freshness: p.freshness_minutes,
    position: p.position,
    club: p.club,
  }));

  const nodeById = new Map(nodes.map(n => [n.id, n]));

  const links = data.edges
    .filter(e => nodeById.has(e.source) && nodeById.has(e.target))
    .map(e => ({
      source: e.source,
      target: e.target,
      value: e.weighted_shared_minutes,
      raw: e.raw_shared_minutes,
    }));

  if (links.length === 0) {
    svg.append("text")
      .attr("x", width / 2).attr("y", height / 2)
      .attr("text-anchor", "middle")
      .style("fill", "#9a9891").style("font-size", "13px")
      .style("font-family", "sans-serif")
      .text("No co-play edges for this squad in the analysis window");
    return;
  }

  const maxVal = d3.max(links, d => d.value) || 1;
  const maxFresh = d3.max(nodes, d => d.freshness) || 1;

  const strokeScale = d3.scalePow().exponent(0.5).domain([0, maxVal]).range([0.8, 5]);
  const rScale = d3.scaleSqrt().domain([0, maxFresh]).range([5, 16]);
  const opacityScale = d3.scaleLinear().domain([0, maxVal]).range([0.18, 0.7]);

  // Position colours: muted, editorial palette
  const posColor  = { GK: "#d48b07", DF: "#1a5fa8", MF: "#2d7a3f", FW: "#c0362c" };
  const posLabel  = { GK: "Goalkeeper", DF: "Defender", MF: "Midfielder", FW: "Forward" };
  const edgeColor = "#6e6a62";
  const edgeHl    = "#d4380d";

  const connected = new Set(links.flatMap(l => [l.source, l.target]));

  const sim = d3.forceSimulation(nodes)
    .force("link",      d3.forceLink(links).id(d => d.id).distance(75).strength(d => (d.value / maxVal) * 0.45))
    .force("charge",    d3.forceManyBody().strength(-200))
    .force("center",    d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide(d => rScale(d.freshness) + 4))
    .force("isolatedX", d3.forceX(width / 2).strength(d => connected.has(d.id) ? 0 : 0.15))
    .force("isolatedY", d3.forceY(height / 2).strength(d => connected.has(d.id) ? 0 : 0.15));

  const linkGroup = svg.append("g").attr("class", "links");
  const link = linkGroup.selectAll("line").data(links).join("line")
    .attr("stroke", edgeColor)
    .attr("stroke-opacity", d => opacityScale(d.value))
    .attr("stroke-width", d => strokeScale(d.value));

  const nodeGroup = svg.append("g").attr("class", "nodes");
  const node = nodeGroup.selectAll("g").data(nodes).join("g")
    .attr("class", "node")
    .style("cursor", "pointer")
    .call(
      d3.drag()
        .on("start", (event, d) => { if (!event.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag",  (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end",   (event, d) => { if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  node.append("circle")
    .attr("r", d => rScale(d.freshness))
    .attr("fill", d => posColor[d.position] || "#9a9891")
    .attr("fill-opacity", 0.82)
    .attr("stroke", "#faf9f7")
    .attr("stroke-width", 1.5);

  node.append("text")
    .attr("dy", d => rScale(d.freshness) + 11)
    .attr("text-anchor", "middle")
    .style("font-size", "9px")
    .style("fill", "#1a1917")
    .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
    .style("font-weight", "600")
    .style("pointer-events", "none")
    .style("text-shadow", "0 1px 2px #faf9f7, 0 -1px 2px #faf9f7, 1px 0 2px #faf9f7, -1px 0 2px #faf9f7")
    .text(d => {
      const parts = d.name.trim().split(/\s+/);
      return parts[parts.length - 1];
    });

  // Tooltip
  const tooltip = d3.select("body").select("#network-tooltip");
  const tip = tooltip.empty()
    ? d3.select("body").append("div").attr("id", "network-tooltip")
    : tooltip;

  tip.style("position", "absolute")
    .style("background", "#ffffff")
    .style("border", "1px solid #c9c6be")
    .style("border-radius", "3px")
    .style("padding", "0.55rem 0.8rem")
    .style("font-size", "12px")
    .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
    .style("pointer-events", "none")
    .style("opacity", 0)
    .style("z-index", "100")
    .style("line-height", "1.55")
    .style("box-shadow", "0 2px 8px rgba(0,0,0,0.1)");

  node
    .on("mouseover", (event, d) => {
      link
        .attr("stroke-opacity", l => l.source.id === d.id || l.target.id === d.id ? 0.85 : 0.04)
        .attr("stroke", l => l.source.id === d.id || l.target.id === d.id ? edgeHl : edgeColor);
      node.select("circle")
        .attr("fill-opacity", n => {
          if (n.id === d.id) return 1;
          const adj = links.some(l =>
            (l.source.id === d.id && l.target.id === n.id) ||
            (l.target.id === d.id && l.source.id === n.id));
          return adj ? 1 : 0.2;
        });

      const mins = d.freshness > 0 ? d.freshness.toLocaleString() + " min" : "No data in window";
      const apps = d.freshness > 0 ? ` (~${Math.round(d.freshness / 90)} apps)` : "";
      tip.transition().duration(80).style("opacity", 1);
      tip.html(`
        <span style="font-weight:700;color:#1a1917">${d.name}</span><br/>
        <span style="color:${posColor[d.position] || '#9a9891'};font-weight:600">${posLabel[d.position] || d.position}</span>
        <span style="color:#9a9891"> · ${d.club}</span><br/>
        <span style="color:#5c5a56">${mins}${apps}</span>
      `).style("left", `${event.pageX + 14}px`).style("top", `${event.pageY - 10}px`);
    })
    .on("mousemove", event => {
      tip.style("left", `${event.pageX + 14}px`).style("top", `${event.pageY - 10}px`);
    })
    .on("mouseout", () => {
      link.attr("stroke-opacity", d => opacityScale(d.value)).attr("stroke", edgeColor);
      node.select("circle").attr("fill-opacity", 0.82);
      tip.transition().duration(150).style("opacity", 0);
    });

  sim.stop();
  for (let i = 0; i < 300; i++) sim.tick();

  const clamp = d => {
    const r = rScale(d.freshness) + 2;
    d.x = Math.max(r, Math.min(width - r, d.x));
    d.y = Math.max(r, Math.min(height - r, d.y));
  };
  nodes.forEach(clamp);

  link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
  node.attr("transform", d => `translate(${d.x},${d.y})`);

  sim.restart();
  sim.on("tick", () => {
    nodes.forEach(clamp);
    link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
        .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    node.attr("transform", d => `translate(${d.x},${d.y})`);
  });

  // Position legend
  const legend = svg.append("g").attr("transform", "translate(16, 16)");
  ["GK", "DF", "MF", "FW"].forEach((pos, i) => {
    const row = legend.append("g").attr("transform", `translate(0, ${i * 18})`);
    row.append("circle").attr("r", 5).attr("cx", 5).attr("cy", 0)
      .attr("fill", posColor[pos]).attr("fill-opacity", 0.85);
    row.append("text").attr("x", 14).attr("dy", "0.35em")
      .style("font-size", "10px")
      .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
      .style("fill", "#5c5a56")
      .text(posLabel[pos]);
  });

  // Size note
  svg.append("text")
    .attr("x", width - 12).attr("y", 20)
    .attr("text-anchor", "end")
    .style("font-size", "9px")
    .style("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif")
    .style("fill", "#9a9891")
    .text("Node size = freshness (minutes played, last 365 days)");
}
