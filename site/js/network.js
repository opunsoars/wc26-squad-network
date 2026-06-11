function renderNetwork(data) {
  const svgEl = document.getElementById("network");
  if (!svgEl || !data) return;

  // Use a fixed coordinate space; CSS scales it to container width via viewBox
  const width = 900;
  const height = 520;
  svgEl.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svgEl.setAttribute("width", "100%");
  svgEl.setAttribute("height", height);
  svgEl.style.display = "block";

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
      .style("fill", "#8b949e").style("font-size", "14px")
      .text("No co-play edges for this squad in the analysis window");
    return;
  }

  const maxVal = d3.max(links, d => d.value) || 1;
  const maxFresh = d3.max(nodes, d => d.freshness) || 1;

  const strokeScale = d3.scalePow().exponent(0.5).domain([0, maxVal]).range([0.4, 5]);
  const rScale = d3.scaleSqrt().domain([0, maxFresh]).range([5, 16]);
  const opacityScale = d3.scaleLinear().domain([0, maxVal]).range([0.08, 0.55]);

  const posColor = { GK: "#f0b429", DF: "#4dabf7", MF: "#69db7c", FW: "#ff6b6b" };
  const posLabel = { GK: "Goalkeeper", DF: "Defender", MF: "Midfielder", FW: "Forward" };

  // Defs: glow filter
  const defs = svg.append("defs");
  const filter = defs.append("filter").attr("id", "glow");
  filter.append("feGaussianBlur").attr("stdDeviation", "3").attr("result", "coloredBlur");
  const feMerge = filter.append("feMerge");
  feMerge.append("feMergeNode").attr("in", "coloredBlur");
  feMerge.append("feMergeNode").attr("in", "SourceGraphic");

  // Build adjacency set so isolated nodes can get extra gravity
  const connected = new Set(links.flatMap(l => [l.source, l.target]));

  const sim = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(70).strength(d => (d.value / maxVal) * 0.5))
    .force("charge", d3.forceManyBody().strength(-180))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide(d => rScale(d.freshness) + 4))
    .force("isolatedX", d3.forceX(width / 2).strength(d => connected.has(d.id) ? 0 : 0.15))
    .force("isolatedY", d3.forceY(height / 2).strength(d => connected.has(d.id) ? 0 : 0.15));

  const linkGroup = svg.append("g").attr("class", "links");
  const link = linkGroup.selectAll("line").data(links).join("line")
    .attr("stroke", "#58a6ff")
    .attr("stroke-opacity", d => opacityScale(d.value))
    .attr("stroke-width", d => strokeScale(d.value));

  const nodeGroup = svg.append("g").attr("class", "nodes");
  const node = nodeGroup.selectAll("g").data(nodes).join("g")
    .attr("class", "node")
    .style("cursor", "pointer")
    .call(
      d3.drag()
        .on("start", (event, d) => { if (!event.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => { if (!event.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  node.append("circle")
    .attr("r", d => rScale(d.freshness))
    .attr("fill", d => posColor[d.position] || "#8b949e")
    .attr("fill-opacity", 0.88)
    .attr("stroke", "#0d1117")
    .attr("stroke-width", 1.5);

  // Short label: last token when splitting on spaces (skip hyphenated suffixes)
  node.append("text")
    .attr("dy", "0.35em")
    .attr("text-anchor", "middle")
    .style("font-size", d => rScale(d.freshness) > 10 ? "9px" : "0")
    .style("fill", "#0d1117")
    .style("font-weight", "600")
    .style("pointer-events", "none")
    .text(d => {
      const parts = d.name.trim().split(/\s+/);
      const last = parts[parts.length - 1];
      // Truncate to 6 chars to fit inside node
      return last.length > 6 ? last.slice(0, 6) : last;
    });

  // Tooltip
  const tooltip = d3.select("body").select("#network-tooltip");
  const tip = tooltip.empty()
    ? d3.select("body").append("div").attr("id", "network-tooltip")
    : tooltip;

  tip.style("position", "absolute")
    .style("background", "#161b22")
    .style("border", "1px solid #30363d")
    .style("border-radius", "6px")
    .style("padding", "0.6rem 0.9rem")
    .style("font-size", "12px")
    .style("pointer-events", "none")
    .style("opacity", 0)
    .style("z-index", "100")
    .style("line-height", "1.6");

  node
    .on("mouseover", (event, d) => {
      // Highlight connected edges
      link
        .attr("stroke-opacity", l =>
          l.source.id === d.id || l.target.id === d.id ? 0.85 : 0.04)
        .attr("stroke", l =>
          l.source.id === d.id || l.target.id === d.id ? "#f0b429" : "#58a6ff");
      node.select("circle")
        .attr("fill-opacity", n => {
          if (n.id === d.id) return 1;
          const connected = links.some(l =>
            (l.source.id === d.id && l.target.id === n.id) ||
            (l.target.id === d.id && l.source.id === n.id));
          return connected ? 1 : 0.25;
        });

      const mins = d.freshness.toLocaleString();
      const hours = (d.freshness / 90).toFixed(0);
      tip.transition().duration(100).style("opacity", 1);
      tip.html(`
        <strong style="color:#e6edf3">${d.name}</strong><br/>
        <span style="color:${posColor[d.position] || '#8b949e'}">${posLabel[d.position] || d.position}</span>
        · ${d.club}<br/>
        <span style="color:#8b949e">Freshness: </span>${mins} min <span style="color:#8b949e">(~${hours} apps)</span>
      `).style("left", `${event.pageX + 14}px`).style("top", `${event.pageY - 10}px`);
    })
    .on("mousemove", event => {
      tip.style("left", `${event.pageX + 14}px`).style("top", `${event.pageY - 10}px`);
    })
    .on("mouseout", () => {
      link.attr("stroke-opacity", d => opacityScale(d.value)).attr("stroke", "#58a6ff");
      node.select("circle").attr("fill-opacity", 0.88);
      tip.transition().duration(200).style("opacity", 0);
    });

  // Run simulation to near-equilibrium synchronously so the initial render
  // is already settled (avoids blank state in screenshots / slow connections)
  sim.stop();
  for (let i = 0; i < 300; i++) sim.tick();

  const clamp = (d) => {
    const r = rScale(d.freshness) + 2;
    d.x = Math.max(r, Math.min(width - r, d.x));
    d.y = Math.max(r, Math.min(height - r, d.y));
  };
  nodes.forEach(clamp);

  // Draw initial settled positions
  link
    .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
    .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
  node.attr("transform", d => `translate(${d.x},${d.y})`);

  // Then re-enable live ticking for interactivity (drag etc.)
  sim.restart();
  sim.on("tick", () => {
    nodes.forEach(clamp);
    link
      .attr("x1", d => d.source.x).attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    node.attr("transform", d => `translate(${d.x},${d.y})`);
  });

  // Legend
  const legend = svg.append("g").attr("transform", `translate(16, 16)`);
  const positions = ["GK", "DF", "MF", "FW"];
  positions.forEach((pos, i) => {
    const row = legend.append("g").attr("transform", `translate(0, ${i * 20})`);
    row.append("circle").attr("r", 6).attr("cx", 6).attr("cy", 0)
      .attr("fill", posColor[pos]).attr("fill-opacity", 0.88).attr("stroke", "#0d1117").attr("stroke-width", 1);
    row.append("text").attr("x", 16).attr("dy", "0.35em")
      .style("font-size", "11px").style("fill", "#8b949e").text(posLabel[pos]);
  });

  // Node size legend
  const sizeLegend = svg.append("g").attr("transform", `translate(${width - 100}, 16)`);
  sizeLegend.append("text").attr("dy", "0.35em").style("font-size", "10px").style("fill", "#8b949e").text("Node size = freshness");
}
